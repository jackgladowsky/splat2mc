# splat2mc

Convert 3D Gaussian Splats to Minecraft particle datapacks.

![demo](docs/demo.gif)

## What is this?

3D Gaussian Splatting (3DGS) is a technique for reconstructing 3D scenes from photos. This tool takes those reconstructions and renders them in Minecraft using the particle system.

## Installation

```bash
# Clone
git clone https://github.com/jackgladowsky/splat2mc.git
cd splat2mc

# Install with uv
uv sync

# Or with pip
pip install -e .
```

## Usage

### Convert a single PLY file

```bash
splat2mc convert scene.ply -o ./datapacks

# Options:
#   -n, --max-particles  Maximum particles (default: 5000)
#   -s, --size          Target size in blocks (default: 10)
#   --min-opacity       Minimum opacity threshold (default: 0.1)
```

### Batch convert

```bash
splat2mc batch ./splats -o ./datapacks
```

### Get info about a PLY file

```bash
splat2mc info scene.ply
```

## In Minecraft

1. Copy the generated datapack to your world's `datapacks/` folder
2. Run `/reload`
3. Run `/function splats:<name>`

The particles spawn relative to your position.

## Getting PLY files

You can get 3DGS PLY files from:
- [Luma AI](https://lumalabs.ai/) - Scan with your phone
- [Polycam](https://poly.cam/) - Another scanning app
- Train your own with [gaussian-splatting](https://github.com/graphdeco-inria/gaussian-splatting)

## How it works

1. **Parse PLY** - Extract position, color (from spherical harmonics), opacity, and scale
2. **Normalize** - Scale and center to fit in Minecraft
3. **Downsample** - Keep the most opaque splats to stay under particle limits
4. **Generate mcfunction** - Output `/particle` commands for each splat
5. **Package** - Create a ready-to-use datapack

## Limitations

- Minecraft particles are spherical, not ellipsoidal like true Gaussians
- Limited to ~5000 particles before performance issues
- No rotation/anisotropy - we just use average scale
- Particles fade quickly - they're meant to be re-triggered

## License

MIT
