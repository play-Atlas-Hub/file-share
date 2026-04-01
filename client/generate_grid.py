from PIL import Image, ImageDraw

# Create grid texture
width, height = 1280, 720
grid_size = 50

# Create image with transparent background
img = Image.new('RGBA', (width, height), (20, 20, 20, 255))
draw = ImageDraw.Draw(img)

# Draw grid
for x in range(0, width, grid_size):
    draw.line([(x, 0), (x, height)], fill=(60, 60, 60, 255), width=1)

for y in range(0, height, grid_size):
    draw.line([(0, y), (width, y)], fill=(60, 60, 60, 255), width=1)

# Save
img.save('grid.png')
print("Grid image created: grid.png")