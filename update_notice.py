"""Pillow rendering for the same 640-point update notice as the Mac version."""
import math
import time
from PIL import Image, ImageDraw, ImageFilter


class UpdateNotice:
    def __init__(self, release=None, error=None):
        self.release, self.error = release, error
        self.phase = 'available' if release else 'failed' if error else 'current'
        self.progress = None
        self.started = time.monotonic()

    @property
    def rect(self):
        return (238,112 if self.release else 190,582,336)

    @property
    def bounds(self):
        return (230,self.rect[1]-8,590,432 if self.release else 350)

    @property
    def buttons(self):
        if self.phase in {'verifying','ready','installing'}:
            return {}
        if self.phase == 'downloading':
            return {'cancel':(258,284,562,318)}
        if not self.release:
            return {'dismiss':(258,284,562,318)}
        return {'dismiss':(258,284,400,318),'update':(420,284,562,318)}

    def draw(self, canvas, current, font, surface, wrap, reduced=False, elapsed=None):
        elapsed = time.monotonic()-self.started if elapsed is None else elapsed
        left,top,right,bottom = self.rect
        canvas.alpha_composite(surface(self.rect))
        draw = ImageDraw.Draw(canvas)
        ink,rose,green = '#4a3b40','#a36170','#459161'
        draw.text((left+20,top+16),'猪猪桌宠 · 软件更新',font=font(11),fill=rose)
        progress = self.phase in {'downloading','verifying','ready','installing'}
        if self.release:
            title = '更新未完成' if self.error else f'正在更新到 {self.release.version}' if progress else f'检测到有新版本 {self.release.version}'
            draw.text((left+20,top+43),title,font=font(17,True),fill=ink)
            messages = {'downloading':'正在下载…'+(f' {self.progress:.0%}' if self.progress is not None else ''),
                        'verifying':'正在校验更新包，请稍候…','ready':'已准备好；正在等待权限处理或拖动结束。',
                        'installing':'正在准备备份与重启，请稍候…'}
            message = self.error or messages.get(self.phase) or self.release.notes
            lines = [line for paragraph in message.splitlines() for line in wrap(draw,paragraph,font(13),304,3)][:3]
            for i,line in enumerate(lines):
                draw.text((left+20,top+78+i*20),line,font=font(13),fill=ink)
            if progress:
                x,y = left+20,top+135
                draw.rounded_rectangle((x,y,x+304,y+6),3,fill='#d9d9d9')
                width = max(1,304*self.progress) if self.progress is not None else 60
                offset = 0 if self.progress is not None or reduced else (math.sin(elapsed*2)+1)/2*(304-width)
                draw.rounded_rectangle((x+offset,y,x+offset+width,y+6),3,fill=green)
            label = '完成后自动重启，设置和任务数据会保留。' if progress else f'是否选择更新版本：{current} → {self.release.version}'
            draw.text((left+20,top+146),label,font=font(12),fill=ink)
        else:
            title = '暂时无法检查更新，请稍后重试' if self.error else '当前已是最新版本啦！'
            draw.text((left+20,top+47),title,font=font(15 if self.error else 17,True),fill=ink)
        for action,rect in self.buttons.items():
            primary = action=='update' or not self.release
            draw.rounded_rectangle(rect,10,fill=green if primary else '#e3e3e3')
            label = '取消下载' if action=='cancel' else ('重试' if self.error else '更新') if action=='update' else '稍后再说' if self.release else '收到！'
            draw.text(((rect[0]+rect[2])/2,(rect[1]+rect[3])/2),label,font=font(13,True),anchor='mm',fill='white' if primary else ink)
        if self.release:
            pulse = .5 if reduced else (math.sin(elapsed*math.pi*1.25)+1)/2
            lift = 0 if reduced else math.sin(elapsed*math.pi*1.25)*2
            # Draw at 3x, rotate counterclockwise 30 degrees, then downsample.
            bulb = Image.new('RGBA',(300,300))
            glow = Image.new('RGBA',(300,300))
            d = ImageDraw.Draw(glow)
            d.ellipse((73,61,227,215),fill=(255,196,50,round(65+60*pulse)))
            bulb.alpha_composite(glow.filter(ImageFilter.GaussianBlur(18+12*pulse)))
            d = ImageDraw.Draw(bulb)
            outline = '#a36e30'
            d.ellipse((105,78,195,168),fill=(255,round(219+18*pulse),92),outline=outline,width=7)
            d.polygon([(113,143),(126,180),(174,180),(187,143)],fill=(255,round(219+18*pulse),92))
            d.line([(113,143),(126,180),(174,180),(187,143)],fill=outline,width=7)
            d.line([(138,177),(135,141),(150,150),(165,141),(162,177)],fill=outline,width=5)
            d.rounded_rectangle((126,180,174,210),9,fill='#dbcca8',outline=outline,width=6)
            d.line((132,195,168,195),fill=outline,width=4)
            d.arc((119,94,149,124),180,270,fill='#fff9e3',width=8)
            for angle in (-150,-110,-70,-30,15,165):
                a=math.radians(angle)
                d.line([(150+math.cos(a)*75,135+math.sin(a)*75),(150+math.cos(a)*(87+9*pulse),135+math.sin(a)*(87+9*pulse))],fill=outline,width=5)
            bulb=bulb.rotate(30,resample=Image.Resampling.BICUBIC).resize((100,100),Image.Resampling.LANCZOS)
            canvas.alpha_composite(bulb,(360,round(340+lift)))
