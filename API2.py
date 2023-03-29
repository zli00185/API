from fastapi import FastAPI, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRouter
from pydantic import BaseModel
from enum import Enum
import numpy as np
from typing import Optional, List
import random
from fastapi.templating import Jinja2Templates
import os
from io import BytesIO
import PIL.Image
import base64
import cv2


app = FastAPI()
router = APIRouter()
templates  = Jinja2Templates(directory= "templates")

crop_image_amount = 0
Noise_image_amount = 0

class Gender(str, Enum):
    male = "male"
    female = "female"

class User(BaseModel):
    username: str
    password: str
    email: str
    gender: Gender
    user_info: Optional[str]

class Image(BaseModel):
    label: Optional[str]
    file_name:str
    file_location: str

# In-memory database of users
USERS_DB: List[User]= [
    User(
        username = "Zeyu", 
        password = "123",
        email = "zli00185@terpmail.umd.edu",
        gender = Gender.male,
        user_info = None
    )   
]

IMAGE_DB: List[Image] = []
SEGIMAGE_DB: List[Image] = []
NOISE_DB: List[Image] = []

@app.get('/', response_class= HTMLResponse)
async def home_page(request: Request):
    #data_set = {'Page': 'Home', 'Message': 'Home Page'}
    context = {'request':request}
    return templates.TemplateResponse("home.html", context)

@app.get('/login', response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post('/login',response_class= HTMLResponse)
async def user_page(request: Request, username: str = Form(...), password: str = Form(...)):

    for user in USERS_DB:
        if username == user.username and password ==user.password:
            context = {'user': user, 'request': request}
            #return {"message": "Login in successful"}
            return templates.TemplateResponse("user.html", context)
            
    raise HTTPException(status_code=401, detail="Invalid username or password")



@app.get("/register", response_class=HTMLResponse)
async def register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post('/register')
async def signup(request: Request, username: str = Form(...), password: str =Form(...), confirm_password: str = Form(...), email:str = Form(...), gender: Gender = Form(...), user_info: Optional[str] = None):
    if(password != confirm_password):
        raise HTTPException(status_code=400, detail="passwords need to be same")
       
    user = User(
        username = username,
        password = password,
        email = email.lower(),
        gender = gender,
        user_info = user_info    
    )
    
    for existing_user in USERS_DB:
        if user.email == existing_user.email:
            raise HTTPException(status_code=400, detail="Email already exists")
        elif user.username == existing_user.username:
            raise HTTPException(status_code=400, detail="Username already exists")
    USERS_DB.append(user)
    context = {'user': user, 'request': request}     
    return templates.TemplateResponse("account_created.html", context)


@app.get('/upload', response_class= HTMLResponse)
async def upload(request: Request):
    context = {"request": request}
    return templates.TemplateResponse("image_upload.html", context)


@app.post('/upload')
async def upload_image(request: Request, label: str = Form(...), file: UploadFile = File(...)):
    
    #file path need to be change
    file_location = f"uploads/{file.filename}"
    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())
    
    new_image = Image(
        label = label,
        file_name= file.filename,
        file_location = file_location
    )
    
    IMAGE_DB.append(new_image)
    add_noise(new_image)
    
    context = {"request": request}
    return templates.TemplateResponse("upload_success.html", context)


@app.get('/test', response_class=HTMLResponse)
async def image_test(request: Request):
    if len(IMAGE_DB)==0:
        return templates.TemplateResponse("no_image.html", {"request": request})
    
    random_image = random.choice(IMAGE_DB)
    image = PIL.Image.open(random_image.file_location)
    buffer = BytesIO()
    image.save(buffer,format = "JPEG")
    image_str = base64.b64encode(buffer.getvalue()).decode()
    
    return templates.TemplateResponse("image_test.html", {"request": request,"true_label": random_image.label ,"image_location": image_str})

@app.post('/test', response_class=HTMLResponse)
async def test(request: Request, true_label: str = Form(...),label: Optional[str] = None):
    context = {"request": request, "label": label, "true_label": true_label}
    return templates.TemplateResponse("answer.html", context)
        
app.include_router(router)


@app.get('/segment', response_class=HTMLResponse)
async def segment(request:Request):
    if len(NOISE_DB)==0 and len(NOISE_DB)==0:
        return templates.TemplateResponse("no_image.html", {"request": request})
    
    if len(IMAGE_DB) != 0:
        random_image = random.choice(IMAGE_DB)
    else:
        random_image = random.choice(NOISE_DB)
    
    image = PIL.Image.open(random_image.file_location)
    buffer = BytesIO()
    image.save(buffer,format = "JPEG")
    image_str = base64.b64encode(buffer.getvalue()).decode()
    
    return templates.TemplateResponse("segmentation.html", {"request": request,"true_label": random_image.label ,"file_name": random_image.file_name,"image_location": image_str, "file_location": random_image.file_location})


@app.post('/segment', response_class=HTMLResponse)
async def save_segmentation(request:Request,length: int = Form(...), width: int = Form(...), center_x: int = Form(...), center_y: int = Form(...), file_location: str = Form(...), file_name: str = Form(...),true_label:str = Form(...)):

    img = PIL.Image.open(file_location)
    cropped_img = img.crop((center_x - length / 2, center_y - width / 2, center_x + length / 2, center_y + width / 2))
    
    global crop_image_amount
    
    new_file_name = str(crop_image_amount)+'_cropped_image.jpg' 
    crop_image_amount = crop_image_amount+1
    
    with BytesIO() as output:
        cropped_img.save(output, format='JPEG')
        contents = output.getvalue()
        file = File(BytesIO(contents), filename= new_file_name)
    
    crop_file_location = f"segmentation/{new_file_name}"
    with open(crop_file_location, "wb+") as file_object:
        cropped_img.save(file_object, format='JPEG')

   
    crop_image = Image(
        file_name = file_name,
        file_location = crop_file_location
    )
    
    SEGIMAGE_DB.append(crop_image)
    
    #delete image once get segment:
    delete = False
    
    for image in IMAGE_DB:
        if image.file_name == file_name:
            IMAGE_DB.remove(image)
            delete = True
            
    if delete == False:        
        for image in NOISE_DB:
            if image.file_name == file_name:
                NOISE_DB.remove(image)
    
    image = PIL.Image.open(crop_image.file_location)
    buffer = BytesIO()
    image.save(buffer,format = "JPEG")
    image_str = base64.b64encode(buffer.getvalue()).decode()
    return templates.TemplateResponse("segment_success.html", {"request": request,"true_label":"cropped" ,"image_location": image_str})

@app.get('/show_segmentation', response_class=HTMLResponse)
async def get_all_segmentation(request:Request):
    if(len(SEGIMAGE_DB)==0):
       return templates.TemplateResponse("no_image.html", {"request": request})
    
    seg_location: List[str] = []
    for img in SEGIMAGE_DB:
        image = PIL.Image.open(img.file_location)
        buffer = BytesIO()
        image.save(buffer,format = "JPEG")
        image_str = base64.b64encode(buffer.getvalue()).decode()
        seg_location.append(image_str)
    
    return templates.TemplateResponse("show_segmentation.html", {"request": request,"seg_location":seg_location })



def add_noise(image: Image):
    noise_mean = 200
    noise_sigma = 50
    
    global Noise_image_amount
    image_open = cv2.imread(image.file_location)
    h, w, c= image_open.shape
    
    gauss_noise=np.zeros((h,w,c),dtype=np.uint8)
    cv2.randn(gauss_noise,noise_mean,noise_sigma)
    gauss_noise=(gauss_noise*0.5).astype(np.uint8)
    
    gn_array=cv2.add(image_open,gauss_noise)
    
    new_file_name = str(Noise_image_amount)+'_Noise_image.jpg' 
    Noise_image_amount = Noise_image_amount+1
    
    gn_img = PIL.Image.fromarray(gn_array)
    
    with BytesIO() as output:
        gn_img.save(output, format='JPEG')
        contents = output.getvalue()
        file = File(BytesIO(contents), filename= new_file_name)
    
    Noise_image_location = f"Noise/{new_file_name}"
    with open(Noise_image_location, "wb+") as file_object:
        gn_img.save(file_object, format='JPEG')
        
        
    Noise_image = Image(
        file_name = new_file_name,
        file_location = Noise_image_location
    )
    
    NOISE_DB.append(Noise_image)