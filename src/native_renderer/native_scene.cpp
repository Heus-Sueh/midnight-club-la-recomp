#include "native_renderer/native_scene.h"

#include <cstring>
#include <limits>

#include <rex/system/xmemory.h>

namespace mcla {

NativeSceneCapture::NativeSceneCapture() {
  pending_draws_.reserve(4096);
}

NativeSceneCapture& NativeSceneCapture::Get() {
  static NativeSceneCapture instance;
  return instance;
}

void NativeSceneCapture::ObserveDrawIndx2(uint32_t device_guest_address, uint32_t argument_r4, uint32_t argument_r5) {
  ObserveDrawCall(kDrawIndx2BuilderAddress, 0xC0003600,
                  device_guest_address, argument_r4, argument_r5, 0, 0,
                  ((argument_r5 & 0xFFFFu) << 16) | argument_r4 | 0x80u);
}

void NativeSceneCapture::ObserveDrawCall(
    uint32_t source_address, uint32_t packet_header,
    uint32_t device_guest_address, uint32_t argument_r4,
    uint32_t argument_r5, uint32_t argument_r6, uint32_t argument_r7,
    uint32_t packet_word) {
  std::lock_guard lock(mutex_);
  if (pending_draws_.size() >= kMaximumDrawsPerFrame) {
    ++pending_dropped_draws_;
    return;
  }

  NativeDrawRecord& draw = pending_draws_.emplace_back();
  draw.source_address = source_address;
  draw.device_guest_address = device_guest_address;
  draw.packet_header = packet_header;
  draw.argument_r4 = argument_r4;
  draw.argument_r5 = argument_r5;
  draw.argument_r6 = argument_r6;
  draw.argument_r7 = argument_r7;
  draw.packet_word = packet_word;
  if (source_address == kDrawPrimitiveUpBuilderAddress) {
    draw.primitive_type = argument_r4 & 0x3Fu;
    draw.vertex_count = argument_r5;
    draw.vertex_stride_bytes = argument_r6;
    const uint64_t vertex_data_size =
        static_cast<uint64_t>(argument_r5) * argument_r6;
    if (vertex_data_size <= std::numeric_limits<uint32_t>::max()) {
      draw.vertex_data_size = static_cast<uint32_t>(vertex_data_size);
    }
  }
}

void NativeSceneCapture::ObserveDrawPrimitiveUpReturn(
    uint32_t vertex_guest_address) {
  std::lock_guard lock(mutex_);
  for (auto draw = pending_draws_.rbegin(); draw != pending_draws_.rend();
       ++draw) {
    if (draw->source_address == kDrawPrimitiveUpBuilderAddress &&
        draw->vertex_guest_address == 0) {
      draw->vertex_guest_address = vertex_guest_address;
      return;
    }
  }
  ++pending_unmatched_vertex_returns_;
}

void NativeSceneCapture::ObserveBuilderCall(uint32_t source_address) {
  for (size_t index = 0; index < kBuilderAddresses.size(); ++index) {
    if (kBuilderAddresses[index] == source_address) {
      builder_calls_[index].fetch_add(1, std::memory_order_relaxed);
      return;
    }
  }
}

std::vector<NativeBuilderActivity> NativeSceneCapture::DrainBuilderActivity() {
  std::vector<NativeBuilderActivity> activity;
  for (size_t index = 0; index < kBuilderAddresses.size(); ++index) {
    const uint64_t calls = builder_calls_[index].exchange(0, std::memory_order_relaxed);
    if (calls != 0) {
      activity.push_back({kBuilderAddresses[index], calls});
    }
  }
  return activity;
}

std::shared_ptr<const NativeFrameScene> NativeSceneCapture::PublishFrame(
    uint64_t guest_present, rex::memory::Memory* memory) {
  auto scene = std::make_shared<NativeFrameScene>();
  std::lock_guard lock(mutex_);
  scene->generation = next_generation_++;
  scene->guest_present = guest_present;
  scene->dropped_draws = pending_dropped_draws_;
  scene->unmatched_vertex_returns = pending_unmatched_vertex_returns_;
  // Copy once at the frame boundary so the hot guest draw path keeps its
  // reserved capacity instead of reallocating the accumulator every frame.
  scene->draws = pending_draws_;

  for (NativeDrawRecord& draw : scene->draws) {
    if (draw.source_address != kDrawPrimitiveUpBuilderAddress) {
      continue;
    }
    ++scene->expected_vertex_buffers;
    if (draw.vertex_guest_address == 0 || draw.vertex_data_size == 0 ||
        memory == nullptr) {
      ++scene->missing_vertex_buffers;
      continue;
    }
    if (draw.vertex_data_size > kMaximumVertexBufferBytes ||
        draw.vertex_guest_address + draw.vertex_data_size <
            draw.vertex_guest_address ||
        scene->vertex_data.size() + draw.vertex_data_size >
            kMaximumVertexDataBytesPerFrame) {
      ++scene->dropped_vertex_buffers;
      continue;
    }

    draw.vertex_data_offset =
        static_cast<uint32_t>(scene->vertex_data.size());
    const uint8_t* source =
        memory->TranslateVirtual<const uint8_t*>(draw.vertex_guest_address);
    scene->vertex_data.resize(scene->vertex_data.size() +
                              draw.vertex_data_size);
    std::memcpy(scene->vertex_data.data() + draw.vertex_data_offset, source,
                draw.vertex_data_size);
    ++scene->captured_vertex_buffers;
  }

  pending_draws_.clear();
  pending_dropped_draws_ = 0;
  pending_unmatched_vertex_returns_ = 0;
  published_scene_ = scene;
  return scene;
}

std::shared_ptr<const NativeFrameScene> NativeSceneCapture::AcquireLatest() const {
  std::lock_guard lock(mutex_);
  return published_scene_;
}

void NativeSceneCapture::Reset() {
  std::lock_guard lock(mutex_);
  pending_draws_.clear();
  pending_dropped_draws_ = 0;
  pending_unmatched_vertex_returns_ = 0;
  next_generation_ = 1;
  published_scene_.reset();
  for (auto& calls : builder_calls_) {
    calls.store(0, std::memory_order_relaxed);
  }
}

}  // namespace mcla
