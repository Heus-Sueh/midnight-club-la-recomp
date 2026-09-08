// midnight_club_la - ReXGlue Recompiled Project
//
// Customize your app by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <rex/cvar.h>
#include <rex/input/flags.h>
#include <rex/rex_app.h>

#include <filesystem>
#include <rex/filesystem.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>

#include "native_renderer/native_renderer.h"

class MidnightClubLaApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<MidnightClubLaApp>(new MidnightClubLaApp(ctx, "midnight_club_la",
        PPCImageConfig));
  }

  void OnPreSetup(rex::RuntimeConfig& config) override {
    REXCVAR_SET(input_backend, std::string("sdl"));
    mcla::NativeRenderer::Get().OnPreSetup(config);
  }

  void OnConfigurePaths(rex::PathConfig& paths) override {
    // Locate configuration file if not already present beside executable
    if (!std::filesystem::exists(paths.config_path)) {
      if (std::filesystem::exists("midnight_club_la.toml")) {
        paths.config_path = std::filesystem::absolute("midnight_club_la.toml");
      } else {
        auto dir = rex::filesystem::GetExecutableFolder();
        for (int i = 0; i < 5; ++i) {
          auto candidate = dir / "midnight_club_la.toml";
          if (std::filesystem::exists(candidate)) {
            paths.config_path = std::filesystem::absolute(candidate);
            break;
          }
          if (!dir.has_parent_path() || dir == dir.parent_path()) {
            break;
          }
          dir = dir.parent_path();
        }
      }
    }

    if (paths.game_data_root.empty() || !std::filesystem::exists(paths.game_data_root)) {
      // 1. Check current working directory
      if (std::filesystem::exists("game/default.xex")) {
        paths.game_data_root = std::filesystem::absolute("game");
        return;
      }
      // 2. Search upwards from the executable folder
      auto dir = rex::filesystem::GetExecutableFolder();
      for (int i = 0; i < 5; ++i) {
        auto candidate = dir / "game";
        if (std::filesystem::exists(candidate / "default.xex")) {
          paths.game_data_root = std::filesystem::absolute(candidate);
          return;
        }
        if (!dir.has_parent_path() || dir == dir.parent_path()) {
          break;
        }
        dir = dir.parent_path();
      }
      // 3. Fallback
      if (paths.game_data_root.empty()) {
        paths.game_data_root = "game";
      }
    }
  }

  // Override virtual hooks for customization:
  // void OnPostInitLogging() override {}
  // void OnLoadXexImage(std::string& xex_image) override {}
  void OnPostLoadXexImage() override {
    mcla::NativeRenderer::Get().OnPostLoadXex();
  }

  void OnPostSetup() override {
    if (runtime() && runtime()->file_system()) {
      runtime()->file_system()->RegisterSymbolicLink("t:", "\\Device\\Harddisk0\\Partition1");
      REXLOG_INFO("[MidnightClubLaApp] Mounted symbolic link 't:' -> '\\Device\\Harddisk0\\Partition1'");
    }
    mcla::NativeRenderer::Get().Initialize(runtime(), window());
  }

  void OnWindowPixelSizeChanged(uint32_t pixel_width, uint32_t pixel_height) override {
    mcla::NativeRenderer::Get().OnWindowResize(pixel_width, pixel_height);
  }

  void OnShutdown() override {
    mcla::NativeRenderer::Get().Shutdown();
  }
};
