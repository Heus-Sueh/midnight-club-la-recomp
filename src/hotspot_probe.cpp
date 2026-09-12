#include "hotspot_probe.h"

#include <atomic>
#include <chrono>
#include <cstdint>

#include <rex/logging.h>

#include "generated/default/midnight_club_la_funcs.h"

namespace {

struct FunctionCounters {
  std::atomic<uint64_t> calls{0};
  std::atomic<uint64_t> inclusive_ns{0};
};

FunctionCounters sub_82415dc8_counters;
FunctionCounters sub_82415ee8_counters;

template <typename Function>
void Measure(FunctionCounters& counters, Function function, PPCContext& ctx, uint8_t* base) {
  const auto started = std::chrono::steady_clock::now();
  function(ctx, base);
  const auto finished = std::chrono::steady_clock::now();
  counters.calls.fetch_add(1, std::memory_order_relaxed);
  counters.inclusive_ns.fetch_add(
      std::chrono::duration_cast<std::chrono::nanoseconds>(finished - started).count(),
      std::memory_order_relaxed);
}

void ReportOne(const char* name, FunctionCounters& counters, double elapsed_seconds) {
  const uint64_t calls = counters.calls.exchange(0, std::memory_order_relaxed);
  const uint64_t inclusive_ns = counters.inclusive_ns.exchange(0, std::memory_order_relaxed);
  const double inclusive_ms = static_cast<double>(inclusive_ns) / 1'000'000.0;
  REXLOG_INFO(
      "[HotspotProbe] {}: calls={}, calls_per_s={:.1f}, inclusive_ms={:.3f}, "
      "avg_us={:.3f}, wall_percent={:.2f}",
      name, calls, elapsed_seconds > 0.0 ? static_cast<double>(calls) / elapsed_seconds : 0.0,
      inclusive_ms, calls ? inclusive_ms * 1000.0 / static_cast<double>(calls) : 0.0,
      elapsed_seconds > 0.0 ? inclusive_ms / (elapsed_seconds * 10.0) : 0.0);
}

}  // namespace

extern "C" void sub_82415DC8(PPCContext& ctx, uint8_t* base) {
  Measure(sub_82415dc8_counters, __imp__sub_82415DC8, ctx, base);
}

extern "C" void sub_82415EE8(PPCContext& ctx, uint8_t* base) {
  Measure(sub_82415ee8_counters, __imp__sub_82415EE8, ctx, base);
}

namespace mcla {

void ReportHotspotProbe(double elapsed_seconds) {
  ReportOne("sub_82415DC8", sub_82415dc8_counters, elapsed_seconds);
  ReportOne("sub_82415EE8", sub_82415ee8_counters, elapsed_seconds);
}

}  // namespace mcla
