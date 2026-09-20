#pragma once

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <mutex>
#include <vector>

namespace rex::memory {
class Memory;
}

namespace mcla {

// Arguments observed at proven RAGE draw entry points. Fields stay raw until
// their semantics are correlated with command-processor traces; promoted
// topology and count fields below have passed that check. packet_word is zero
// when the final value also depends on device state not present at entry.
struct NativeDrawRecord {
  static constexpr uint32_t kInvalidVertexDataOffset = UINT32_MAX;

  uint32_t source_address = 0;
  uint32_t device_guest_address = 0;
  uint32_t packet_header = 0;
  uint32_t argument_r4 = 0;
  uint32_t argument_r5 = 0;
  uint32_t argument_r6 = 0;
  uint32_t argument_r7 = 0;
  uint32_t packet_word = 0;

  // Semantics proven from the packet construction at each promoted builder.
  // index_count names the VGT draw count for both auto-indexed and explicit
  // index-buffer draws; indexed distinguishes the two sources.
  uint32_t index_count = 0;
  bool indexed = false;

  // Proven contract for the DrawPrimitiveUP-style builder at 0x8241CD88.
  // The return hook observes the guest allocation address after the builder
  // has emitted its packet. The data itself is copied only at Present, after
  // the caller has filled the returned allocation.
  uint32_t primitive_type = 0;
  uint32_t vertex_count = 0;
  uint32_t vertex_stride_bytes = 0;
  uint32_t vertex_guest_address = 0;
  uint32_t vertex_data_offset = kInvalidVertexDataOffset;
  uint32_t vertex_data_size = 0;
};

// A frame is immutable after publication. The guest thread can immediately
// begin capturing the next frame while a future Vulkan render thread consumes
// this snapshot without touching guest-owned mutable state.
struct NativeFrameScene {
  uint64_t generation = 0;
  uint64_t guest_present = 0;
  uint64_t dropped_draws = 0;
  uint64_t unmatched_vertex_returns = 0;
  uint64_t missing_vertex_buffers = 0;
  uint64_t dropped_vertex_buffers = 0;
  uint64_t expected_vertex_buffers = 0;
  uint64_t captured_vertex_buffers = 0;
  std::vector<NativeDrawRecord> draws;
  std::vector<uint8_t> vertex_data;
};

struct NativeBuilderActivity {
  uint32_t source_address = 0;
  uint64_t calls = 0;
};

class NativeSceneCapture {
 public:
  static constexpr uint32_t kDrawIndx2BuilderAddress = 0x82427898;
  static constexpr uint32_t kDrawPrimitiveUpBuilderAddress = 0x8241CD88;
  static constexpr size_t kMaximumDrawsPerFrame = 65536;
  static constexpr size_t kMaximumVertexBufferBytes = 1 * 1024 * 1024;
  static constexpr size_t kMaximumVertexDataBytesPerFrame = 16 * 1024 * 1024;
  inline static constexpr std::array<uint32_t, 10> kBuilderAddresses = {
      0x82413068, 0x82417538, 0x82418350, 0x8241CD88, 0x8241D230,
      0x8241D620, 0x82422488, 0x824225E0, 0x82427898, 0x8242DE08,
  };

  static NativeSceneCapture& Get();

  void ObserveDrawIndx2(uint32_t device_guest_address, uint32_t argument_r4, uint32_t argument_r5);
  void ObserveDrawCall(uint32_t source_address, uint32_t packet_header,
                       uint32_t device_guest_address, uint32_t argument_r4,
                       uint32_t argument_r5, uint32_t argument_r6,
                       uint32_t argument_r7, uint32_t packet_word);
  void ObserveDrawPrimitiveUpReturn(uint32_t vertex_guest_address);
  void ObserveBuilderCall(uint32_t source_address);
  std::vector<NativeBuilderActivity> DrainBuilderActivity();
  std::shared_ptr<const NativeFrameScene> PublishFrame(
      uint64_t guest_present, rex::memory::Memory* memory,
      bool capture_vertex_data = true);
  std::shared_ptr<const NativeFrameScene> AcquireLatest() const;
  void Reset();

 private:
  NativeSceneCapture();

  mutable std::mutex mutex_;
  std::vector<NativeDrawRecord> pending_draws_;
  uint64_t pending_dropped_draws_ = 0;
  uint64_t pending_unmatched_vertex_returns_ = 0;
  uint64_t next_generation_ = 1;
  std::shared_ptr<const NativeFrameScene> published_scene_;
  std::array<std::atomic<uint64_t>, kBuilderAddresses.size()> builder_calls_{};
};

}  // namespace mcla
