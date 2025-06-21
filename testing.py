from fastapi.testclient import TestClient
from main import app, SessionLocal, LicenseKey, LicenseUsageLog  # ปรับชื่อไฟล์ main ตามจริง
import pytest

client = TestClient(app)

def setup_test_data(db):
    # ล้างข้อมูลเก่า (ถ้าต้องการ)
    print("[Setup] ล้างข้อมูล LicenseUsageLog และ LicenseKey เก่า")
    db.query(LicenseUsageLog).delete()
    db.query(LicenseKey).delete()
    db.commit()

    # สร้าง LicenseKey ปลอม พร้อม ip_limit = 3
    license = LicenseKey(
        license_key="test-license-123",
        active_system_id=None,
        ip_limit=3
    )
    db.add(license)
    db.commit()
    db.refresh(license)
    print(f"[Setup] สร้าง LicenseKey: {license.license_key} พร้อม ip_limit={license.ip_limit}")

    # สร้าง log IP 2 IP ปลอม เพื่อให้ใกล้เต็ม limit
    log1 = LicenseUsageLog(
        license_key=license.license_key,
        active_system_id=None,
        ip_address="1.1.1.1",
        details="Test log 1"
    )
    log2 = LicenseUsageLog(
        license_key=license.license_key,
        active_system_id=None,
        ip_address="2.2.2.2",
        details="Test log 2"
    )
    db.add_all([log1, log2])
    db.commit()
    print("[Setup] สร้าง LicenseUsageLog สำหรับ IP: 1.1.1.1, 2.2.2.2")

    return license

def test_check_license_ip_limit():
    print("=== เริ่มทดสอบ check_license IP limit ===")
    db = SessionLocal()
    license = setup_test_data(db)

    # IP 1.1.1.1 (เคยใช้งานแล้ว) ควรผ่าน
    print("ทดสอบ IP ซ้ำ 1.1.1.1 (เคยใช้งานแล้ว)")
    response = client.post(
        "/check_license",
        json={"license_key": license.license_key},
        headers={"x-forwarded-for": "1.1.1.1"}
    )
    print("Response:", response.json())
    assert response.status_code == 200
    assert response.json()["valid"] == True

    # IP ใหม่ 3.3.3.3 (ยังไม่ถึง limit) ควรผ่าน
    print("ทดสอบ IP ใหม่ 3.3.3.3 (ยังไม่ถึง limit)")
    response = client.post(
        "/check_license",
        json={"license_key": license.license_key},
        headers={"x-forwarded-for": "3.3.3.3"}
    )
    print("Response:", response.json())
    assert response.status_code == 200
    assert response.json()["valid"] == True

    # IP ใหม่ 4.4.4.4 (เกิน limit 3 IP) ควรถูกบล็อก
    print("ทดสอบ IP ใหม่ 4.4.4.4 (เกิน limit 3 IP)")
    response = client.post(
        "/check_license",
        json={"license_key": license.license_key},
        headers={"x-forwarded-for": "4.4.4.4"}
    )
    print("Response:", response.json())
    assert response.status_code == 200
    assert response.json()["valid"] == False
    assert "ใช้ครบ 3 IP แล้ว" in response.json()["message"]

    db.close()
    print("=== ทดสอบทั้งหมดผ่าน ===")

if __name__ == "__main__":
    test_check_license_ip_limit()
