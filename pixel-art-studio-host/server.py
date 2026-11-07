"""Free deterministic Pixel Art Studio MCP service: no accounts or paid APIs."""
import io
import json
import math
import os
import random
import secrets
import time
import zipfile
from PIL import Image, ImageDraw
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

mcp = MCPServer("Pixel Art Studio")
PALETTES = {
    "forest": ("#172331", "#53728a", "#78ae70", "#497d61", "#f1c59c", "#674c47", "#f4c56e"),
    "dusk": ("#281a3f", "#67547b", "#bf7993", "#87517e", "#e8b49a", "#4a355f", "#f7be78"),
    "cave": ("#181a26", "#4c6470", "#88a48b", "#476478", "#d8c8a0", "#596775", "#ddab73"),
}
KINDS = ("hero", "skeleton", "slime", "bat", "chest", "coin", "potion", "sword", "tree")
ACTIONS = {
    "hero": ("idle", "walk", "run", "attack", "hurt"),
    "skeleton": ("idle", "walk", "attack", "hurt"),
    "slime": ("idle", "jump", "hurt"),
    "bat": ("fly", "hurt"),
    "chest": ("idle", "open"),
    "coin": ("spin",),
    "potion": ("idle",),
    "sword": ("idle",),
    "tree": ("idle",),
}
JOBS = {}

def png(image):
    buffer=io.BytesIO()
    image.save(buffer,format="PNG")
    return buffer.getvalue()

def sprite(kind,action,step,frames,palette):
    ink,shadow,hi,mid,skin,hair,gold = PALETTES[palette]
    im=Image.new("RGBA",(32,32),(0,0,0,0))
    d=ImageDraw.Draw(im)
    phase=2*math.pi*step/frames
    swing=round(math.sin(phase)*3) if action in ("walk","run") else 0
    bounce=round(abs(math.sin(phase))*2) if action in ("walk","run","jump","fly") else (step%3==1)
    if kind in ("hero","skeleton"):
        y=-int(bounce)
        d.rectangle((11-swing,24+y,16-swing,30+y),fill=ink)
        d.rectangle((19+swing,24+y,24+swing,30+y),fill=ink)
        d.rectangle((8+swing,16+y,11+swing,24+y),fill=skin)
        d.rectangle((23-swing,16+y,26-swing,24+y),fill=skin)
        d.rectangle((11,14+y,23,25+y),fill=ink)
        d.rectangle((12,15+y,22,23+y),fill=mid)
        d.rectangle((12,22+y,22,24+y),fill=hair)
        d.rectangle((16,22+y,18,24+y),fill=gold)
        d.rectangle((12,5+y,22,15+y),fill=ink)
        d.rectangle((13,7+y,21,14+y),fill=skin if kind=="hero" else "#d9ddd1")
        d.rectangle((13,5+y,21,8+y),fill=hair if kind=="hero" else ink)
        d.point((16,11+y),fill=ink);d.point((20,11+y),fill=ink)
        if action=="attack":
            x=25+round(5*math.cos(step/frames*math.pi))
            yy=17-round(9*math.sin(step/frames*math.pi))
            d.line((25,21+y,x,yy+y),fill="#b9d7d2",width=2)
    elif kind=="slime":
        t=round(math.sin(phase)*2)
        d.ellipse((7,14-t-bounce,25,29+t-bounce),fill=ink)
        d.ellipse((9,15-t-bounce,23,27+t-bounce),fill=mid)
        d.rectangle((11,17-t-bounce,16,18-t-bounce),fill=hi)
        for x in (13,20):d.rectangle((x,23-t-bounce,x+1,24-t-bounce),fill=ink)
    elif kind=="bat":
        y=10+int(math.sin(phase)*2);flap=int(math.sin(phase)*6)
        d.polygon(((14,y+7),(6,y+1-flap),(2,y+5-flap),(7,y+13)),fill=shadow)
        d.polygon(((20,y+7),(27,y+1-flap),(31,y+5-flap),(26,y+13)),fill=shadow)
        d.ellipse((11,y+4,23,y+17),fill=ink);d.ellipse((13,y+6,21,y+14),fill=mid)
        d.point((15,y+10),fill=gold);d.point((19,y+10),fill=gold)
    elif kind=="tree":
        d.rectangle((14,15,19,30),fill=hair)
        d.ellipse((4,5,29,23),fill=ink);d.ellipse((6,6,27,21),fill=mid)
        d.ellipse((8,7,18,16),fill=hi)
    elif kind=="chest":
        d.rectangle((7,17,25,27),fill=ink);d.rectangle((9,19,23,25),fill=hair)
        top=13-(min(6,step*2) if action=="open" else 0)
        d.rectangle((7,top,25,top+5),fill=ink);d.rectangle((9,top+1,23,top+4),fill=hair)
        d.rectangle((15,18,18,22),fill=gold)
    elif kind=="coin":
        w=max(2,round(abs(math.cos(phase))*10))
        d.ellipse((16-w//2,10,16+w//2,24),fill=ink)
        d.ellipse((17-w//2,11,15+w//2,22),fill=gold)
    elif kind=="potion":
        d.rectangle((13,7,20,11),fill=ink)
        d.polygon(((13,11),(9,17),(9,26),(13,29),(20,29),(24,26),(24,17),(20,11)),fill=ink)
        d.polygon(((14,13),(11,18),(11,25),(14,27),(19,27),(22,25),(22,18),(19,13)),fill=mid)
        d.rectangle((12,19,13,24),fill=hi)
    elif kind=="sword":
        d.polygon(((14,9),(21,3),(23,3),(23,6),(18,11),(18,21),(14,21)),fill=hi)
        d.rectangle((10,20,22,22),fill=gold);d.rectangle((15,22,17,29),fill=hair)
    return im

def pack_asset(kind, frames, size, fps, palette, archive):
    actions=ACTIONS[kind]
    sheet=Image.new("RGBA",(size*frames,size*len(actions)),(0,0,0,0))
    frame_data={};tags=[]
    for row,action in enumerate(actions):
        pictures=[]
        for col in range(frames):
            im=sprite(kind,action,col,frames,palette).resize((size,size),Image.Resampling.NEAREST)
            sheet.alpha_composite(im,(col*size,row*size))
            pictures.append(im)
            archive.writestr(f"sprites/{kind}/frames/{action}_{col:02}.png",png(im))
            frame_data[f"{action}_{col:02}"]={"frame":{"x":col*size,"y":row*size,"w":size,"h":size},"duration":round(1000/fps)}
        anim=io.BytesIO()
        pictures[0].save(anim,format="GIF",save_all=True,append_images=pictures[1:],duration=round(1000/fps),loop=0,disposal=2)
        archive.writestr(f"sprites/{kind}/{action}.gif",anim.getvalue())
        tags.append({"name":action,"from":row*frames,"to":(row+1)*frames-1,"row":row})
    archive.writestr(f"sprites/{kind}/spritesheet.png",png(sheet))
    archive.writestr(f"sprites/{kind}/spritesheet.json",json.dumps({"frames":frame_data,"meta":{"size":{"w":sheet.width,"h":sheet.height},"frameTags":tags,"image":"spritesheet.png","fps":fps}}))

def world(seed,palette,archive):
    ink,shadow,hi,mid,skin,hair,gold=PALETTES[palette]
    tile=16;tw=20;th=12;rng=random.Random(seed)
    colors=[mid,hair,shadow,"#3e86a8"]
    tiles=Image.new("RGBA",(tile*4,tile),(0,0,0,0))
    for k,c in enumerate(colors):
        d=ImageDraw.Draw(tiles);x=k*tile
        d.rectangle((x,0,x+15,15),fill=c)
        for n in range(12):
            xx=x+rng.randrange(16);yy=rng.randrange(16)
            d.point((xx,yy),fill=hi if k in (0,3) else skin)
    archive.writestr("world/tileset.png",png(tiles))
    canvas=Image.new("RGBA",(tw*tile,th*tile));grid=[]
    for y in range(th):
        for x in range(tw):
            k=3 if ((x-13)/4)**2+((y-5)/3)**2<1 else 1 if y==th//2 else 2 if rng.random()<.08 else 0
            grid.append(k+1)
            canvas.alpha_composite(tiles.crop((k*tile,0,(k+1)*tile,tile)),(x*tile,y*tile))
    archive.writestr("world/preview.png",png(canvas))
    tmap={"width":tw,"height":th,"tilewidth":tile,"tileheight":tile,"orientation":"orthogonal","renderorder":"right-down","type":"map","version":"1.10","infinite":False,
          "layers":[{"type":"tilelayer","name":"ground","id":1,"data":grid,"width":tw,"height":th,"visible":True,"opacity":1,"x":0,"y":0}],
          "tilesets":[{"firstgid":1,"columns":4,"image":"tileset.png","imagewidth":64,"imageheight":16,"name":"starter-tiles","tilewidth":tile,"tileheight":tile,"margin":0,"spacing":0,"tilecount":4}]}
    archive.writestr("world/tilemap.tmj",json.dumps(tmap))
    width=320;height=180
    layers=[]
    for j in range(3):
        layer=Image.new("RGBA",(width,height),(0,0,0,0));d=ImageDraw.Draw(layer)
        if j==0:d.rectangle((0,0,width,height),fill=shadow)
        elif j==1:
            pts=[(0,height)]+[(x,120+round(math.sin(x/26)*12)) for x in range(0,width+1,8)]+[(width,height)]
            d.polygon(pts,fill=mid)
        else:
            for x in range(0,width,24):
                d.rectangle((x+11,139,x+15,180),fill=hair)
                d.polygon(((x,150),(x+13,105+(x%17)),(x+26,150)),fill=hi)
        archive.writestr(f"background/parallax-{j}.png",png(layer));layers.append(layer)
    merged=Image.new("RGBA",(width,height))
    for im in layers:merged.alpha_composite(im)
    archive.writestr("background/preview.png",png(merged))
    archive.writestr("background/parallax.json",json.dumps({"layers":[{"file":f"parallax-{j}.png","speed":s} for j,s in enumerate((0.1,0.35,0.8))]}))

@mcp.tool()
def generate_pixel_art_pack(kinds: list[str] = ["hero","slime","coin"], palette: str = "forest", size: int = 32, frames: int = 6, fps: int = 8, seed: int = 5, include_world: bool = True) -> dict:
    """Make sprites, frame PNGs, animated GIFs, sprite sheets, Tiled map and parallax PNGs in a downloadable ZIP. Free and deterministic."""
    if not kinds or len(kinds)>4 or any(k not in KINDS for k in kinds):
        raise ValueError("Choose 1-4 kinds from: "+", ".join(KINDS))
    if palette not in PALETTES or size not in (16,32,64) or not 2<=frames<=12 or not 1<=fps<=24 or not 0<=seed<=1_000_000:
        raise ValueError("Invalid parameters. Palette forest/dusk/cave, size 16/32/64, frames 2-12, fps 1-24.")
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as z:
        for kind in kinds:pack_asset(kind,frames,size,fps,palette,z)
        if include_world:world(seed,palette,z)
        z.writestr("manifest.json",json.dumps({"kinds":kinds,"palette":palette,"size":size,"frames":frames,"fps":fps,"seed":seed,"include_world":include_world}))
    token=secrets.token_urlsafe(24)
    now=time.time()
    for key,(created,_) in list(JOBS.items()):
        if now-created>3600:JOBS.pop(key,None)
    if len(JOBS)>=30:JOBS.pop(next(iter(JOBS)))
    JOBS[token]=(now,buffer.getvalue())
    host=os.getenv("RENDER_EXTERNAL_HOSTNAME","")
    return {"download_url":f"https://{host}/download/{token}" if host else f"/download/{token}", "bytes":len(buffer.getvalue()),"expires_in_seconds":3600,"kinds":kinds,"palette":palette,"size":size,"animations":{k:list(ACTIONS[k]) for k in kinds},"note":"Procedural starter art. Files are temporary; download before the free server sleeps."}

@mcp.tool()
def list_pixel_art_presets() -> dict:
    """List available palettes, sprite types and animation cycle names."""
    return {"palettes":list(PALETTES),"sprites":{k:list(v) for k,v in ACTIONS.items()},"sizes":[16,32,64],"fps":[1,24],"frames":[2,12]}

@mcp.custom_route("/health",methods=["GET"])
async def health(request:Request)->Response:
    return JSONResponse({"status":"ok","service":"pixel-art-studio","cost":"free-tier"})

@mcp.custom_route("/download/{token}",methods=["GET"])
async def download(request:Request)->Response:
    item=JOBS.get(request.path_params["token"])
    if item is None or time.time()-item[0]>3600:
        return JSONResponse({"error":"expired or not found"},status_code=404)
    return Response(item[1],media_type="application/zip",headers={"Content-Disposition":"attachment; filename=pixel-art-pack.zip","Cache-Control":"no-store"})

hostname=os.getenv("RENDER_EXTERNAL_HOSTNAME","localhost")
security=TransportSecuritySettings(
    allowed_hosts=[hostname,hostname+":*","localhost","localhost:*","127.0.0.1","127.0.0.1:*"],
    allowed_origins=["https://chatgpt.com","https://www.chatgpt.com"],
)
app=mcp.streamable_http_app(transport_security=security)
