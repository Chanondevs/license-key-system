from fastapi.testclient import TestClient
from main import app, SessionLocal, LicenseKey, LicenseUsageLog  # ปรับชื่อไฟล์ main ตามจริง
import pytest

client = TestClient(app)

def setup_test_data(db):
    print("[Setup] เริ่มต้นสร้าง LicenseKey และ Logs (ไม่ล้างข้อมูลเก่า)")

    # ลบข้อมูลเก่าออก (ถ้าต้องการ) - ปิดไว้ตามคำขอ
    # db.query(LicenseUsageLog).delete()
    # db.query(LicenseKey).delete()
    # db.commit()

    # ตรวจสอบว่า LicenseKey test-license-123 มีอยู่แล้วไหม ถ้าไม่มีสร้างใหม่
    license = db.query(LicenseKey).filter(LicenseKey.license_key == "test-license-123").first()
    if not license:
        license = LicenseKey(
            license_key="test-license-123",
            active_system_id=None,
            ip_limit=3
        )
        db.add(license)
        db.commit()
        db.refresh(license)
        print(f"[Setup] สร้าง LicenseKey ใหม่: {license.license_key} พร้อม ip_limit={license.ip_limit}")
    else:
        print(f"[Setup] พบ LicenseKey เดิม: {license.license_key} พร้อม ip_limit={license.ip_limit}")

    # ตรวจสอบว่ามี log ของ IP 1.1.1.1 กับ 2.2.2.2 หรือยัง ถ้ายังไม่มีให้สร้างเพิ่ม
    existing_ips = {log.ip_address for log in db.query(LicenseUsageLog).filter(LicenseUsageLog.license_key == license.license_key).all()}
    
    new_logs = []
    if "1.1.1.1" not in existing_ips:
        new_logs.append(LicenseUsageLog(
            license_key=license.license_key,
            active_system_id=None,
            ip_address="1.1.1.1",
            details="License key ถูกต้อง ตรวจสอบมาจาก Server Plugin"
        ))
    if "2.2.2.2" not in existing_ips:
        new_logs.append(LicenseUsageLog(
            license_key=license.license_key,
            active_system_id=None,
            ip_address="2.2.2.2",
            details="License key ถูกต้อง ตรวจสอบมาจาก Server Plugin"
        ))
    if new_logs:
        db.add_all(new_logs)
        db.commit()
        print(f"[Setup] สร้าง LicenseUsageLog สำหรับ IP: {[log.ip_address for log in new_logs]}")
    else:
        print("[Setup] LicenseUsageLog สำหรับ IP 1.1.1.1 และ 2.2.2.2 มีอยู่แล้ว")

    return license

def cleanup_test_data(db):
    print("[Cleanup] ลบข้อมูล LicenseKey และ LicenseUsageLog ทั้งหมด")
    db.query(LicenseUsageLog).delete()
    db.query(LicenseKey).delete()
    db.commit()
    print("[Cleanup] ข้อมูลถูกลบเรียบร้อย")

def test_check_license_ip_limit():
    print("=== เริ่มทดสอบ check_license IP limit ===")
    db = SessionLocal()
    license = setup_test_data(db)

    headers = {"X-Client-Type": "plugin"}  # ใส่ header นี้ทุก request เพื่อให้ log details เป็น Server Plugin

    # IP 1.1.1.1 (เคยใช้งานแล้ว) ควรผ่าน
    print("ทดสอบ IP ซ้ำ 1.1.1.1 (เคยใช้งานแล้ว)")
    response = client.post(
        "/check_license",
        json={"license_key": license.license_key},
        headers={**headers, "x-forwarded-for": "1.1.1.1"}
    )
    print("Response:", response.json())
    assert response.status_code == 200
    assert response.json()["valid"] == True

    # IP ใหม่ 3.3.3.3 (ยังไม่ถึง limit) ควรผ่าน
    print("ทดสอบ IP ใหม่ 3.3.3.3 (ยังไม่ถึง limit)")
    response = client.post(
        "/check_license",
        json={"license_key": license.license_key},
        headers={**headers, "x-forwarded-for": "3.3.3.3"}
    )
    print("Response:", response.json())
    assert response.status_code == 200
    assert response.json()["valid"] == True

    # IP ใหม่ 4.4.4.4 (เกิน limit 3 IP) ควรถูกบล็อก
    print("ทดสอบ IP ใหม่ 4.4.4.4 (เกิน limit 3 IP)")
    response = client.post(
        "/check_license",
        json={"license_key": license.license_key},
        headers={**headers, "x-forwarded-for": "4.4.4.4"}
    )
    print("Response:", response.json())
    assert response.status_code == 200
    assert response.json()["valid"] == False
    assert "ใช้ครบ 3 IP แล้ว" in response.json()["message"]

    db.close()
    print("=== ทดสอบทั้งหมดผ่าน ===")

if __name__ == "__main__":
    # test_check_license_ip_limit()
    cleanup_test_data(SessionLocal())