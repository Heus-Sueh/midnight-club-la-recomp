#include "native_renderer/native_pass_batch.h"

#include "native_renderer/native_scene.h"

#include <array>
#include <bit>
#include <cmath>
#include <cstring>
#include <limits>

namespace mcla {
namespace {

constexpr uint32_t kTriangleStripPrimitive = 6;
constexpr uint32_t kVertexCount = 4;
constexpr uint32_t kVertexStrideBytes = 36;
constexpr uint32_t kPositionWord = 0;
constexpr uint32_t kColorWord = 6;
constexpr uint32_t kTextureWord = 7;

uint32_t LoadK8In32Word(const uint8_t* source) {
  uint32_t word;
  std::memcpy(&word, source, sizeof(word));
  return std::byteswap(word);
}

float LoadK8In32Float(const uint8_t* source) {
  return std::bit_cast<float>(LoadK8In32Word(source));
}

uint32_t ConvertColorZyxwToRgba8(uint32_t color) {
  // vfetch_mini writes the k_8_8_8_8 source to r1.zyxw. Store the resulting
  // r1 components as little-endian RGBA8 for a future native vertex format.
  const uint32_t x = color & 0xFFu;
  const uint32_t y = (color >> 8) & 0xFFu;
  const uint32_t z = (color >> 16) & 0xFFu;
  const uint32_t w = (color >> 24) & 0xFFu;
  return z | (y << 8) | (x << 16) | (w << 24);
}

bool DecodeVertex(const uint8_t* source, NativeStripVertex& vertex) {
  vertex.position_x = LoadK8In32Float(source + (kPositionWord + 0) * 4);
  vertex.position_y = LoadK8In32Float(source + (kPositionWord + 1) * 4);
  vertex.position_z = LoadK8In32Float(source + (kPositionWord + 2) * 4);
  vertex.color_rgba8 = ConvertColorZyxwToRgba8(
      LoadK8In32Word(source + kColorWord * 4));
  vertex.texture_u = LoadK8In32Float(source + (kTextureWord + 0) * 4);
  vertex.texture_v = LoadK8In32Float(source + (kTextureWord + 1) * 4);
  return std::isfinite(vertex.position_x) &&
         std::isfinite(vertex.position_y) &&
         std::isfinite(vertex.position_z) &&
         std::isfinite(vertex.texture_u) && std::isfinite(vertex.texture_v);
}

}  // namespace

NativeStripBatch BuildDominantStripBatch(const NativeFrameScene& scene) {
  NativeStripBatch batch;
  batch.scene_generation = scene.generation;
  batch.source_draw_indices.reserve(scene.draws.size());

  for (size_t draw_index = 0; draw_index < scene.draws.size(); ++draw_index) {
    const NativeDrawRecord& draw = scene.draws[draw_index];
    if (draw.source_address !=
        NativeSceneCapture::kDrawPrimitiveUpBuilderAddress) {
      continue;
    }
    ++batch.candidate_draws;

    if (draw.primitive_type != kTriangleStripPrimitive ||
        draw.vertex_count != kVertexCount ||
        draw.vertex_stride_bytes != kVertexStrideBytes) {
      ++batch.unsupported_draws;
      continue;
    }

    constexpr uint32_t kExpectedDataSize =
        kVertexCount * kVertexStrideBytes;
    if (draw.vertex_data_offset ==
            NativeDrawRecord::kInvalidVertexDataOffset ||
        draw.vertex_data_size != kExpectedDataSize ||
        draw.vertex_data_offset > scene.vertex_data.size() ||
        kExpectedDataSize >
            scene.vertex_data.size() - draw.vertex_data_offset) {
      ++batch.missing_data_draws;
      continue;
    }

    std::array<NativeStripVertex, kVertexCount> decoded_vertices;
    const uint8_t* draw_data =
        scene.vertex_data.data() + draw.vertex_data_offset;
    bool vertices_valid = true;
    for (uint32_t vertex_index = 0; vertex_index < kVertexCount;
         ++vertex_index) {
      vertices_valid &= DecodeVertex(
          draw_data + vertex_index * kVertexStrideBytes,
          decoded_vertices[vertex_index]);
    }
    if (!vertices_valid ||
        batch.vertices.size() >
            std::numeric_limits<uint32_t>::max() - kVertexCount) {
      ++batch.invalid_vertex_draws;
      continue;
    }

    const uint32_t first_vertex =
        static_cast<uint32_t>(batch.vertices.size());
    batch.vertices.insert(batch.vertices.end(), decoded_vertices.begin(),
                          decoded_vertices.end());
    // Convert each independent four-vertex strip to an ordered triangle list.
    // Never join strips: doing so would create cross-draw triangles.
    batch.indices.insert(batch.indices.end(),
                         {first_vertex + 0, first_vertex + 1,
                          first_vertex + 2, first_vertex + 2,
                          first_vertex + 1, first_vertex + 3});
    batch.source_draw_indices.push_back(static_cast<uint32_t>(draw_index));
    ++batch.accepted_draws;
  }

  return batch;
}

}  // namespace mcla
