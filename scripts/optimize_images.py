import os
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
TOPPERS_DIR = BASE_DIR / 'static' / 'images' / 'toppers'

def optimize_topper_images():
    if not TOPPERS_DIR.exists():
        print(f"Directory {TOPPERS_DIR} does not exist.")
        return

    print("Starting image optimization for toppers...")
    for img_path in TOPPERS_DIR.glob('*.jpg'):
        orig_size = img_path.stat().st_size
        try:
            with Image.open(img_path) as img:
                # Resize if long side > 1200px
                max_dim = 1200
                if img.width > max_dim or img.height > max_dim:
                    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                
                # Convert RGBA/P to RGB
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Save optimized image
                img.save(img_path, format='JPEG', quality=80, optimize=True)
            
            new_size = img_path.stat().st_size
            print(f"Optimized {img_path.name}: {orig_size / (1024*1024):.2f}MB -> {new_size / 1024:.1f}KB")
        except Exception as e:
            print(f"Error optimizing {img_path.name}: {e}")

if __name__ == '__main__':
    optimize_topper_images()
