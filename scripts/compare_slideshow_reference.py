"""Compare independent Qt raster compositions with external synthetic WPF captures.

The input directory must contain synthetic-<WxH>.png plus the named effect PNGs
produced by the reference-only capture tool. No proprietary assets are imported.
Usage: py scripts/compare_slideshow_reference.py <reference-directory> <output-dir>
"""
import json
import os
from pathlib import Path
import sys

if '--opengl' not in sys.argv:
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageChops, ImageDraw, ImageStat
from PyQt6.QtGui import QImage, QSurfaceFormat, QColorSpace
from PyQt6.QtWidgets import QApplication
from image_classifier.imaging.loader import ImageFrame
from image_classifier.slideshow.controller import SlideEntry
from image_classifier.slideshow.motion import EFFECTS
from image_classifier.slideshow.surface import SlideSurface


def main():
    reference,output=map(Path,sys.argv[1:3])
    opengl='--opengl' in sys.argv
    output.mkdir(parents=True,exist_ok=True)
    if opengl:
        format=QSurfaceFormat()
        format.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        format.setVersion(3,3)
        format.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.SRgb))
        QSurfaceFormat.setDefaultFormat(format)
    app=QApplication([])
    surface=SlideSurface(raster=not opengl)
    surface.resize(960,540)
    surface.show()
    app.processEvents()
    metrics=[]
    for shape in ('1200x800','800x1200','1000x1000','2400x600'):
        source=QImage(str(reference/f'synthetic-{shape}.png'))
        if source.isNull(): raise ValueError('Missing synthetic input '+shape)
        for progress in (.25,.5,.75):
            sheet=Image.new('RGB',(1600,6*112),'#222222')
            draw=ImageDraw.Draw(sheet)
            for index,effect in enumerate(EFFECTS.values()):
                name=f'{shape}-effect{effect.number:02}-p{progress*100:03.0f}.png'
                surface.present(SlideEntry('',effect.identifier),ImageFrame('',source,True))
                surface.refresh(progress,100)
                app.processEvents()
                qt_path=output/('qt-'+name)
                if opengl:
                    if not surface.canvas.isValid(): raise RuntimeError('Native OpenGL context did not initialize')
                    surface.canvas.grabFramebuffer().save(str(qt_path))
                else:
                    surface.canvas.grab().save(str(qt_path))
                qt=Image.open(qt_path).convert('RGB')
                wpf=Image.open(reference/name).convert('RGB')
                if qt.size != wpf.size:
                    raise RuntimeError(f'DPI mismatch: Qt {qt.size}, WPF {wpf.size}')
                # WPF reference controls occupy the bottom 70 pixels. Exclude
                # these UI elements from the foreground comparison metric.
                region=(0,0,qt.width,round(qt.height*470/540))
                diff=ImageChops.difference(qt.crop(region),wpf.crop(region))
                mae=sum(ImageStat.Stat(diff).mean)/3
                metrics.append(dict(shape=shape,effect=effect.identifier,progress=progress,mean_absolute_rgb_error=mae))
                x=(index%5)*320;y=(index//5)*112
                draw.text((x+2,y+2),effect.identifier+' WPF | Qt',fill='white')
                sheet.paste(wpf.resize((160,90)),(x,y+20))
                sheet.paste(qt.resize((160,90)),(x+160,y+20))
            sheet.save(output/f'comparison-{shape}-{progress}.png')
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    print(json.dumps({'samples':len(metrics),'renderer':type(surface.canvas).__name__,
                      'maximum_mean_absolute_rgb_error':max(r['mean_absolute_rgb_error'] for r in metrics)},indent=2))
    surface.close()


if __name__=='__main__':main()
