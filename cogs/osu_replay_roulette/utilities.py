from typing import Optional
import time

def get_future_time(seconds: int) -> str:
    current_time: int = int(time.time())
    future_time: int = current_time + seconds
    discord_timestamp: str = f"<t:{future_time}:R>"
    return discord_timestamp

def simplify_number(number: int) -> str:
    if number >= 1000000:
        return f"{round(number/1000000, 2)}M"
    elif number >= 1000:
        return f"{round(number/1000, 2)}K"
    else:
        return str(number)
    
def number_from_string(number: str) -> Optional[int]:
    try:
        number = number.lower().strip()
        number = number.replace(",", "").replace(" ", "").replace("_", "")
        
        multiplier: int = 1
        if number.endswith('k'):
            multiplier = 1000
            number = number[:-1]
        elif number.endswith('m'):
            multiplier = 1000000
            number = number[:-1]
        
        if '.' in number:
            result = float(number) * multiplier
            if result < 1:
                return None
            return int(float(number) * multiplier)
        else:
            result = int(number) * multiplier
            if result < 1:
                return None
            return int(number) * multiplier
    except:
        return None