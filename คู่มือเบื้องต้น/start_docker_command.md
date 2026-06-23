# Docker Commands (NAS Server)
## 1) หยุดระบบ (แต่ข้อมูล Database ยังอยู่)

ใช้เมื่อต้องการปิดระบบชั่วคราว
--------------------------------
docker compose down            
--------------------------------
* ปิด container ทั้งหมด          
* **ข้อมูลใน Database ยังไม่หาย**
* เปิดกลับมาใช้งานใหม่ได้ตามปกติ    



## 2) เปิดระบบ

ใช้เมื่อต้องการรันระบบขึ้นมาใหม่
------------------------------------------------------------
docker compose up -d
------------------------------------------------------------
* เปิด container ทั้งหมดแบบ background (`-d = detached mode`)
* ระบบจะรันต่อโดยไม่ล็อก terminal



## 3) ดู Log ของ App
ใช้ตรวจสอบ error หรือดูสถานะการทำงาน
----------------------------------------
docker compose logs -f app
----------------------------------------
* ดู log แบบ realtime
* ใช้ debug เวลา app เปิดไม่ขึ้น / มี error



## 4) Rebuild หลังแก้โค้ด
ใช้เมื่อมีการแก้ไข source code หรือ Dockerfile
----------------------------------------
docker compose up -d --build
----------------------------------------
* Build image ใหม่
* แล้วเปิดระบบให้อัตโนมัติ
* ใช้หลังแก้ backend / frontend / dependency



## 5) ล้าง Database ทั้งหมด (ใช้เฉพาะตอนทดสอบ)
### ถ้าล้างไปแล้ว ต้องไปไฟล์ import_db_docker.md เพื่อใช้คำสั่ง import Database เข้ามาใหม่ ###
⚠️ **ระวังมาก — ข้อมูลทั้งหมดจะหาย**
----------------------------------------
docker compose down -v
----------------------------------------
* ปิด container
* ลบ volume ทั้งหมด
* **Database ใน Docker จะถูกลบทิ้งถาวร**

ใช้เฉพาะกรณี:
* reset ระบบใหม่
* ทดสอบ clean install
* ไม่ต้องการข้อมูลเก่าแล้ว

## 6) rebuild เก็บไฟล์ frontend/dist
-------------------------------------
npm.cmd --prefix .\frontend run build
-------------------------------------

###### Quick Summary (สรุปสั้น ๆ) #######
| คำสั่ง                           | ใช้ทำอะไร             |
| ------------------------------ | ---------------------|
| `docker compose down`          | ปิดระบบ               |
| `docker compose up -d`         | เปิดระบบ              |
| `docker compose logs -f app`   | ดู log                |
| `docker compose up -d --build` | build ใหม่หลังแก้โค้ด   |
| `docker compose down -v`       | ล้าง DB ทั้งหมด        |


## Recommended Workflow
แก้โค้ด → Rebuild → เช็ค Log
------------------------------
docker compose up -d --build
docker compose logs -f app
------------------------------
