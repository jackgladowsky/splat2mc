"""Core converter: PLY → mcfunction."""

import numpy as np
from plyfile import PlyData
from pathlib import Path
from dataclasses import dataclass


@dataclass
class GaussianSplat:
    """A single Gaussian splat with position, color, opacity, and scale."""
    x: float
    y: float
    z: float
    r: float  # 0-1
    g: float  # 0-1
    b: float  # 0-1
    opacity: float  # 0-1
    scale: float  # average scale


def load_ply(path: Path) -> list[GaussianSplat]:
    """Load Gaussian splats from a PLY file.
    
    3DGS PLY files typically contain:
    - x, y, z: position
    - f_dc_0, f_dc_1, f_dc_2: spherical harmonics DC component (color)
    - opacity: opacity (logit space, needs sigmoid)
    - scale_0, scale_1, scale_2: log scale
    - rot_0, rot_1, rot_2, rot_3: rotation quaternion
    """
    plydata = PlyData.read(str(path))
    vertex = plydata['vertex']
    
    # Extract positions
    x = np.array(vertex['x'])
    y = np.array(vertex['y'])
    z = np.array(vertex['z'])
    
    # Extract colors from spherical harmonics DC component
    # SH coefficients need conversion: color = 0.5 + SH_DC * C0
    # where C0 = 0.28209479177387814
    C0 = 0.28209479177387814
    
    if 'f_dc_0' in vertex.data.dtype.names:
        # 3DGS format with spherical harmonics
        r = 0.5 + np.array(vertex['f_dc_0']) * C0
        g = 0.5 + np.array(vertex['f_dc_1']) * C0
        b = 0.5 + np.array(vertex['f_dc_2']) * C0
    elif 'red' in vertex.data.dtype.names:
        # Standard PLY with RGB
        r = np.array(vertex['red']) / 255.0
        g = np.array(vertex['green']) / 255.0
        b = np.array(vertex['blue']) / 255.0
    else:
        # Fallback: white
        r = np.ones_like(x)
        g = np.ones_like(x)
        b = np.ones_like(x)
    
    # Clamp colors to valid range
    r = np.clip(r, 0, 1)
    g = np.clip(g, 0, 1)
    b = np.clip(b, 0, 1)
    
    # Extract opacity (stored as logit, apply sigmoid)
    if 'opacity' in vertex.data.dtype.names:
        opacity_logit = np.array(vertex['opacity'])
        opacity = 1 / (1 + np.exp(-opacity_logit))
    else:
        opacity = np.ones_like(x)
    
    # Extract scale (stored as log, take exp and average)
    if 'scale_0' in vertex.data.dtype.names:
        scale_0 = np.exp(np.array(vertex['scale_0']))
        scale_1 = np.exp(np.array(vertex['scale_1']))
        scale_2 = np.exp(np.array(vertex['scale_2']))
        scale = (scale_0 + scale_1 + scale_2) / 3
    else:
        scale = np.ones_like(x) * 0.01
    
    # Build splat list
    splats = []
    for i in range(len(x)):
        splats.append(GaussianSplat(
            x=float(x[i]),
            y=float(y[i]),
            z=float(z[i]),
            r=float(r[i]),
            g=float(g[i]),
            b=float(b[i]),
            opacity=float(opacity[i]),
            scale=float(scale[i]),
        ))
    
    return splats


def normalize_splats(
    splats: list[GaussianSplat],
    target_size: float = 10.0,
    center: bool = True,
) -> list[GaussianSplat]:
    """Normalize splat positions to fit in a reasonable Minecraft space.
    
    Args:
        splats: List of splats
        target_size: Target size in Minecraft blocks
        center: Whether to center at origin
    """
    if not splats:
        return splats
    
    # Get bounds
    xs = [s.x for s in splats]
    ys = [s.y for s in splats]
    zs = [s.z for s in splats]
    
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)
    
    # Calculate scale factor
    range_x = max_x - min_x or 1
    range_y = max_y - min_y or 1
    range_z = max_z - min_z or 1
    max_range = max(range_x, range_y, range_z)
    scale_factor = target_size / max_range
    
    # Calculate center offset
    if center:
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        center_z = (min_z + max_z) / 2
    else:
        center_x = center_y = center_z = 0
    
    # Normalize
    normalized = []
    for s in splats:
        normalized.append(GaussianSplat(
            x=(s.x - center_x) * scale_factor,
            y=(s.y - center_y) * scale_factor,
            z=(s.z - center_z) * scale_factor,
            r=s.r,
            g=s.g,
            b=s.b,
            opacity=s.opacity,
            scale=s.scale * scale_factor,
        ))
    
    return normalized


def downsample_splats(
    splats: list[GaussianSplat],
    max_count: int = 5000,
    method: str = "opacity",
) -> list[GaussianSplat]:
    """Downsample splats to fit Minecraft particle limits.
    
    Args:
        splats: List of splats
        max_count: Maximum number of splats to keep
        method: "opacity" (keep most opaque) or "random"
    """
    if len(splats) <= max_count:
        return splats
    
    if method == "opacity":
        # Sort by opacity descending, keep top N
        sorted_splats = sorted(splats, key=lambda s: s.opacity, reverse=True)
        return sorted_splats[:max_count]
    else:
        # Random sample
        indices = np.random.choice(len(splats), max_count, replace=False)
        return [splats[i] for i in indices]


def generate_mcfunction(
    splats: list[GaussianSplat],
    relative: bool = True,
    min_opacity: float = 0.1,
) -> str:
    """Generate mcfunction content with particle commands.
    
    Args:
        splats: List of normalized splats
        relative: Use relative coordinates (~) vs absolute
        min_opacity: Skip splats below this opacity
    """
    lines = [
        "# Generated by splat2mc",
        f"# {len(splats)} Gaussian splats",
        "",
    ]
    
    for s in splats:
        if s.opacity < min_opacity:
            continue
        
        # Format position
        if relative:
            pos = f"~{s.x:.3f} ~{s.y:.3f} ~{s.z:.3f}"
        else:
            pos = f"{s.x:.3f} {s.y:.3f} {s.z:.3f}"
        
        # Clamp and format color
        r = max(0, min(1, s.r))
        g = max(0, min(1, s.g))
        b = max(0, min(1, s.b))
        
        # Scale particle size (clamp to Minecraft's 0.01-4 range)
        particle_scale = max(0.1, min(4.0, s.scale * 50))
        
        # Generate particle command
        line = f"particle dust{{color:[{r:.3f},{g:.3f},{b:.3f}],scale:{particle_scale:.2f}}} {pos} 0 0 0 0 1 force"
        lines.append(line)
    
    return "\n".join(lines)


def generate_datapack(
    name: str,
    mcfunction_content: str,
    output_dir: Path,
) -> Path:
    """Generate a complete Minecraft datapack.
    
    Args:
        name: Name of the splat/datapack
        mcfunction_content: The mcfunction file content
        output_dir: Output directory
    
    Returns:
        Path to the created datapack directory
    """
    # Sanitize name for filesystem/minecraft
    safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in name.lower())
    
    # Create datapack structure
    datapack_dir = output_dir / f"splat_{safe_name}"
    functions_dir = datapack_dir / "data" / "splats" / "function"
    functions_dir.mkdir(parents=True, exist_ok=True)
    
    # Write pack.mcmeta
    pack_mcmeta = datapack_dir / "pack.mcmeta"
    pack_mcmeta.write_text('''{
  "pack": {
    "pack_format": 48,
    "description": "3D Gaussian Splat: ''' + name + '''"
  }
}
''')
    
    # Write mcfunction
    mcfunction_file = functions_dir / f"{safe_name}.mcfunction"
    mcfunction_file.write_text(mcfunction_content)
    
    # Write a helper function to show available splats
    (functions_dir / "help.mcfunction").write_text(
        f'tellraw @s {{"text":"Available splats: {safe_name}","color":"green"}}\n'
        f'tellraw @s {{"text":"Run: /function splats:{safe_name}","color":"gray"}}'
    )
    
    return datapack_dir


def convert_ply_to_datapack(
    ply_path: Path,
    output_dir: Path,
    max_particles: int = 5000,
    target_size: float = 10.0,
    min_opacity: float = 0.1,
) -> Path:
    """Full pipeline: PLY → datapack.
    
    Args:
        ply_path: Path to input PLY file
        output_dir: Output directory for datapack
        max_particles: Maximum number of particles
        target_size: Target size in Minecraft blocks
        min_opacity: Minimum opacity to include
    
    Returns:
        Path to created datapack
    """
    # Load
    print(f"Loading {ply_path}...")
    splats = load_ply(ply_path)
    print(f"  Loaded {len(splats)} splats")
    
    # Normalize
    print(f"Normalizing to {target_size} blocks...")
    splats = normalize_splats(splats, target_size=target_size)
    
    # Downsample
    if len(splats) > max_particles:
        print(f"Downsampling to {max_particles} particles...")
        splats = downsample_splats(splats, max_count=max_particles)
    
    # Generate mcfunction
    print("Generating mcfunction...")
    mcfunction = generate_mcfunction(splats, min_opacity=min_opacity)
    
    # Generate datapack
    name = ply_path.stem
    print(f"Creating datapack '{name}'...")
    datapack_path = generate_datapack(name, mcfunction, output_dir)
    
    print(f"Done! Datapack at: {datapack_path}")
    return datapack_path
