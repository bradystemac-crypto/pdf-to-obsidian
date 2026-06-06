# icon.py

from PIL import Image, ImageDraw

def create_icon():
    img = Image.new("RGB", (64, 64), color="#0f0f0f")
    draw = ImageDraw.Draw(img)
    
    # Simple notebook icon
    draw.rectangle([12, 8, 52, 56], fill="#7c6aff")
    draw.rectangle([16, 12, 48, 52], fill="#0f0f0f")
    draw.line([20, 20, 44, 20], fill="#7c6aff", width=2)
    draw.line([20, 28, 44, 28], fill="#7c6aff", width=2)
    draw.line([20, 36, 36, 36], fill="#7c6aff", width=2)
    
    img.save("icon.png")
    print("icon.png created")

if __name__ == "__main__":
    create_icon()