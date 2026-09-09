{
  description = "Independent, interoperable client for Soundcore-family Bluetooth accessories";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {
    self,
    nixpkgs,
  }: let
    inherit (nixpkgs) lib;

    systems = ["x86_64-linux" "aarch64-linux"];
    forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

    soundcore-client = {
      lib,
      buildPythonPackage,
      hatchling,
      pytestCheckHook,
    }:
      buildPythonPackage {
        pname = "soundcore-client";
        version = "0.1.0";
        pyproject = true;

        src = lib.fileset.toSource {
          root = ./.;
          fileset = lib.fileset.unions [
            ./pyproject.toml
            # Pending review
            (lib.fileset.maybeMissing ./README.md)
            ./soundcore
            ./tests
          ];
        };

        build-system = [hatchling];
        nativeCheckInputs = [pytestCheckHook];
        pythonImportsCheck = ["soundcore" "soundcore.cli"];

        meta = {
          description = "Clean-room RFCOMM/SPP control client for Soundcore earbuds, headphones and speakers";
          license = lib.licenses.mit;
          mainProgram = "soundcore";
          platforms = lib.platforms.linux;
        };
      };

    perSystem = forAllSystems (
      pkgs: let
        python = pkgs.python3;
        pkg = python.pkgs.callPackage soundcore-client {};
        devPython = python.withPackages (ps: [ps.pytest]);

        lintSrc = lib.fileset.toSource {
          root = ./.;
          fileset = lib.fileset.unions [./pyproject.toml ./soundcore ./tests ./examples];
        };
      in {
        package = pkg;

        app = {
          type = "app";
          program = lib.getExe pkg;
        };

        devShell = pkgs.mkShell {
          packages = [
            devPython
            pkgs.ruff
            pkgs.basedpyright
          ];
          shellHook = ''
            export PYTHONPATH="$PWD''${PYTHONPATH:+:$PYTHONPATH}"
            echo "soundcore-client · python ${python.version}"
            echo "  python -m soundcore --help   pytest   ruff check .   basedpyright ."
          '';
        };

        checks = {
          package = pkg;
          lint = pkgs.runCommand "ruff-check" {nativeBuildInputs = [pkgs.ruff];} ''
            cd ${lintSrc}
            ruff check --no-cache .
            touch $out
          '';
        };

        formatter = pkgs.nixpkgs-fmt;
      }
    );
  in {
    overlays.default = final: prev: {
      python3Packages = prev.python3Packages.overrideScope (
        pyFinal: _pyPrev: {
          soundcore-client = pyFinal.callPackage soundcore-client {};
        }
      );
      soundcore-client = final.python3Packages.soundcore-client;
    };

    packages =
      lib.mapAttrs (_: v: {
        default = v.package;
        soundcore-client = v.package;
      })
      perSystem;

    apps = lib.mapAttrs (_: v: {default = v.app;}) perSystem;
    devShells = lib.mapAttrs (_: v: {default = v.devShell;}) perSystem;
    checks = lib.mapAttrs (_: v: v.checks) perSystem;
    formatter = lib.mapAttrs (_: v: v.formatter) perSystem;
  };
}
