import os
import random
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from typing import List, Tuple

 
    
def get_bg(set_id:int):
    bace_url = f"https://assets.ppy.sh/beatmaps/{set_id}/covers/raw.jpg"
    r = requests.get(bace_url)
    img = Image.open(BytesIO(r.content))
    return img

def get_preview(set_id:int, out_dir:str):
    bace_url = f"https://b.ppy.sh/preview/{set_id}.mp3"
    r = requests.get(bace_url)
    with open(f"{out_dir}/preview.mp3", "wb") as f:
        f.write(r.content)
    
    with open(f"{out_dir}/preview.mp3", "rb") as f:
        if len(f.read()) < 1000:
            return "preview.mp3", False
        
    return "preview.mp3", True


def resize_with_padding(image:Image.Image, desired_size:Tuple[int,int], fill_color=(0, 0, 0), resample=Image.LANCZOS):
    ratio = min(desired_size[0] / image.width, desired_size[1] / image.height)
    new_size = (int(image.width * ratio), int(image.height * ratio))
    resized_image = image.resize(new_size, resample=resample)
    new_image = Image.new("RGB", desired_size, fill_color)
    paste_position = ((desired_size[0] - new_size[0]) // 2,
                        (desired_size[1] - new_size[1]) // 2)
    new_image.paste(resized_image, paste_position)
    
    return new_image


def get_image_grid(map_set_ids:List[int], real_set_id:int, out_dir:str):
    imgs = [get_bg(real_set_id)] + [get_bg(set_id) for set_id in map_set_ids]
    
    imgs = [img.convert("RGB") for img in imgs]
    
    smallest_height = 540
    smallest_width = 960
    
    imgs = [resize_with_padding(img, (smallest_width, smallest_height)) for img in imgs]
    
    real_image = imgs.pop(0)
    random.shuffle(imgs)
    
    new_index_for_real_image = random.randint(0, len(imgs))
    
    imgs.insert(new_index_for_real_image, real_image)
    
    new_combined_image = Image.new("RGB", (smallest_width * 3, smallest_height * 2))
    for i, img in enumerate(imgs):
        font_size = int(((smallest_height + smallest_width) / 2) * 0.2)
        font = ImageFont.truetype("arial.ttf", font_size)
        draw = ImageDraw.Draw(img)
        draw.line((0, 0, 0, smallest_height), fill=(0, 0, 0), width=font_size//30)
        draw.line((0, 0, smallest_width, 0), fill=(0, 0, 0), width=font_size//30)
        draw.line((smallest_width, 0, smallest_width, smallest_height), fill=(0, 0, 0), width=font_size//30)
        draw.line((0, smallest_height, smallest_width, smallest_height), fill=(0, 0, 0), width=font_size//30)
        draw.text((font_size*0.03, font_size*0.03), str(i+1), (0, 0, 0), font=font)
        draw.text((0, 0), str(i+1), (255, 255, 255), font=font)
        new_combined_image.paste(img, (smallest_width * (i % 3), smallest_height * (i // 3)))
        
    new_combined_image.save(f"{out_dir}/combined_image.jpg")
        

    return f"{out_dir}/combined_image.jpg", new_index_for_real_image
