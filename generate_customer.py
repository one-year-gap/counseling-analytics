import csv
import random
import os
import json
import base64
import bcrypt
from datetime import datetime, timedelta, date
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# --- 암호화 설정 (자바의 AES/ECB/PKCS5Padding 과 동일하게 맞춤) ---
# 32바이트 비밀키 (SECRET_KEY 환경변수 값 적용)
AES_SECRET_KEY = b'Xy9zPvQ3kL5mRnJwT8bH2cD4fG7jA1sE'

def encrypt_aes(raw_text):
    # 자바의 AES/ECB/PKCS5Padding 과 호환되는 암호화 함수
    cipher = AES.new(AES_SECRET_KEY, AES.MODE_ECB)
    
    # 파이썬의 PKCS7 패딩은 자바의 PKCS5 패딩과 완벽하게 호환됨
    encrypted_bytes = cipher.encrypt(pad(raw_text.encode('utf-8'), AES.block_size))
    return base64.b64encode(encrypted_bytes).decode('utf-8')

# 10만번 연산 방지를 위해 '1234'의 BCrypt 해시를 미리 한 번만 생성
# 자바 Spring Security의 BCryptPasswordEncoder와 호환됨
DEFAULT_PASSWORD_HASH = bcrypt.hashpw(b"1234", bcrypt.gensalt()).decode('utf-8')

# --- 설정 및 상수 ---
SIZES = [10, 100, 1000, 10000, 50000, 100000]
OUTPUT_DIR = "dummy_data_customer"

# 이름 생성을 위한 한국인 성/이름 풀
LAST_NAMES = ['김', '이', '박', '최', '정', '강', '조', '윤', '장', '임', '한', '오', '서', '신', '권', '황', '안', '송', '전', '홍']
FIRST_NAMES = ['하영', '민준', '서준', '도윤', '예준', '시우', '하준', '지호', '주원', '지훈', '건우', '서연', '서윤', '지우', '서현', '하은', '하윤', '민서', '지유', '윤서', '지민', '영현', '수아', '은우', '다은']

# 대한민국 17개 시/도 지역 풀
ADDRESS_POOL = {
    '서울': {'강남구': ['테헤란로', '강남대로'], '서초구': ['서초대로', '반포대로'], '송파구': ['올림픽로', '송파대로'], '마포구': ['월드컵북로', '마포대로']},
    '부산': {'해운대구': ['해운대해변로', '센텀중앙로'], '부산진구': ['서전로', '중앙대로'], '동래구': ['충렬대로', '명륜로']},
    '대구': {'수성구': ['동대구로', '달구벌대로'], '중구': ['국채보상로', '동성로'], '달서구': ['월배로', '상인로']},
    '인천': {'연수구': ['컨벤시아대로', '인천타워대로'], '남동구': ['인주대로', '구월로'], '부평구': ['부평대로', '경원대로']},
    '광주': {'서구': ['상무중앙로', '무진대로'], '북구': ['첨단과기로', '동문대로'], '광산구': ['사암로', '첨단중앙로']},
    '대전': {'유성구': ['대덕대로', '대학로'], '서구': ['둔산대로', '대덕대로'], '중구': ['계룡로', '중앙로']},
    '울산': {'남구': ['삼산로', '번영로'], '중구': ['번영로', '학성로'], '동구': ['방어진순환도로', '대학길']},
    '세종특별자치시': {'세종시': ['한누리대로', '가름로', '다솜로', '도움로']},
    '경기': {'성남시 분당구': ['판교역로', '성남대로'], '수원시 영통구': ['광교중앙로', '도청로'], '용인시 수지구': ['포은대로', '수지로'], '고양시 일산동구': ['정발산로', '일산로']},
    '강원특별자치도': {'춘천시': ['중앙로', '퇴계로'], '원주시': ['원일로', '서원대로'], '강릉시': ['경강로', '율곡로']},
    '충북': {'청주시 흥덕구': ['대농로', '가경로'], '충주시': ['국원대로', '예성로'], '제천시': ['의림대로', '청전대로']},
    '충남': {'천안시 서북구': ['불당대로', '충무로'], '아산시': ['온천대로', '충무로'], '당진시': ['당진중앙2로', '원당로']},
    '전북특별자치도': {'전주시 완산구': ['백제대로', '기린대로'], '익산시': ['무왕로', '선화로'], '군산시': ['대학로', '수송로']},
    '전남': {'여수시': ['시청로', '망마로'], '순천시': ['순광로', '백강로'], '목포시': ['백년대로', '영산로']},
    '경북': {'포항시 남구': ['포스코대로', '새천년대로'], '구미시': ['구미대로', '송정대로'], '경주시': ['원화로', '태종로']},
    '경남': {'창원시 성산구': ['창원대로', '중앙대로'], '진주시': ['진주대로', '동진로'], '김해시': ['내외중앙로', '가락로']},
    '제주특별자치도': {'제주시': ['노연로', '도령로', '연북로'], '서귀포시': ['일주동로', '중앙로']}
}

# 상품 ID 범위
MOBILE_IDS = list(range(1, 51))
TAB_WATCH_IDS = list(range(51, 60))
IPTV_IDS = list(range(60, 66))
INTERNET_IDS = list(range(66, 75))
ADDON_IDS = list(range(75, 121))
TETHERING_SUPPORTED_IDS = [1, 2, 3, 4, 5, 6, 8, 13, 14, 18, 23, 27, 29, 30, 32, 34, 37, 39, 43]

os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_random_date(start_date, end_date):
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days
    random_number_of_days = random.randrange(days_between_dates)
    return start_date + timedelta(days=random_number_of_days)

def get_last_12_months():
    today = datetime.now()
    months = []
    for i in range(12):
        d = today - timedelta(days=30 * i)
        months.append(d.strftime('%Y%m'))
    return sorted(months)

def get_weighted_join_date():
    # 가입일 가중치 로직: 장기(10년)부터 최근까지 현실적인 비율로 생성
    today = date.today()
    # 1. 7~10년 전 장기고객 (약 15%)
    # 2. 3~7년 전 중기고객 (약 35%)
    # 3. 0~3년 전 신규/최근고객 (약 50%)
    category = random.choices(['LONG', 'MID', 'SHORT'], weights=[15, 35, 50], k=1)[0]
    
    if category == 'LONG':
        start = today - timedelta(days=3650) # 약 10년 전 (2016년)
        end = today - timedelta(days=2555)   # 약 7년 전
    elif category == 'MID':
        start = today - timedelta(days=2555)
        end = today - timedelta(days=1095)   # 약 3년 전
    else:
        start = today - timedelta(days=1095)
        end = today
        
    return generate_random_date(start, end)

def run_generation(target_users):
    print(f"[{target_users}명] 데이터 생성 시작...")
    dir_path = os.path.join(OUTPUT_DIR, f"size_{target_users}")
    os.makedirs(dir_path, exist_ok=True)

    # 1. 주소 데이터 생성 (가족 공유를 위해 회원 수의 80% 생성)
    num_addresses = max(1, int(target_users * 0.8))
    seen_address_key = set()  # (province, city, street_address) 유니크 제약 준수
    print(" - 주소 데이터 생성 중...")
    with open(os.path.join(dir_path, 'address.csv'), 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['province', 'city', 'street_address', 'postal_code', 'created_at', 'updated_at'])
        
        for i in range(1, num_addresses + 1):
            while True:
                prov = random.choice(list(ADDRESS_POOL.keys()))
                city = random.choice(list(ADDRESS_POOL[prov].keys()))
                street_base = random.choice(ADDRESS_POOL[prov][city])
                street = f"{street_base} {random.randint(1, 150)}길 {random.randint(1, 99)}"
                key = (prov, city, street)
                if key not in seen_address_key:
                    seen_address_key.add(key)
                    break
            postal = f"{random.randint(10000, 69999)}"
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
         
            writer.writerow([prov, city, street, postal, now_str, now_str])

    # 2. 회원 데이터 생성 (암호화 적용)
    print(" - 회원 데이터 생성 중...")
    used_emails = set()
    used_phones = set()
    
    subscriptions_to_create = [] # (member_id, [product_ids], start_date)
    
    with open(os.path.join(dir_path, 'member.csv'), 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['address_id', 'provider_id', 'email', 'password', 'name', 'phone', 'birth_date', 'gender', 'join_date', 'created_at', 'updated_at', 'status_updated_at', 'status', 'type', 'role', 'membership'])
        
        for member_id in range(1, target_users + 1):
            # [A] 기본 정보 생성
            raw_name = random.choice(LAST_NAMES) + random.choice(FIRST_NAMES)
            encrypted_name = encrypt_aes(raw_name)
            
            while True:
                email = f"user{member_id}_{random.randint(1000,9999)}@gmail.com"
                if email not in used_emails:
                    used_emails.add(email)
                    break
                    
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            join_date = get_weighted_join_date()

            # 💡 [B] 상태, 역할, 가입유형 완전 고정!
            role = 'CUSTOMER'
            status = 'ACTIVE'
            signup_type = 'FORM'
            provider_id = '' # 폼 가입이므로 소셜 ID는 무조건 빈칸
            hashed_password = DEFAULT_PASSWORD_HASH # 비밀번호는 무조건 1234
            
            # [C] 고객 필수 정보 100% 채우기
            address_id = random.randint(1, num_addresses)
            
            while True:
                raw_phone = f"010-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
                if raw_phone not in used_phones:
                    used_phones.add(raw_phone)
                    break
            encrypted_phone = encrypt_aes(raw_phone)
            
            birth_date = generate_random_date(date(1960, 1, 1), date(2010, 12, 31))
            gender = random.choice(['M', 'F'])
            membership = random.choices(['VVIP', 'VIP', 'GOLD'], weights=[10, 20, 70], k=1)[0]
            
            # [D] 요금제(구독) 생성 (100% 고객이므로 조건문 없이 무조건 생성)
            my_products = []
            my_products.append(random.choice(MOBILE_IDS)) # 모바일 1개 필수
            if random.random() < 0.2: my_products.append(random.choice(TAB_WATCH_IDS))
            if random.random() < 0.2: my_products.append(random.choice(IPTV_IDS))
            if random.random() < 0.2: my_products.append(random.choice(INTERNET_IDS))
            num_addons = random.randint(0, 4)
            my_products.extend(random.sample(ADDON_IDS, num_addons))
            
            sub_start = generate_random_date(join_date, date.today())
            subscriptions_to_create.append((member_id, my_products, sub_start))

            # CSV 쓰기
            writer.writerow([
                address_id, provider_id, email, hashed_password, 
                encrypted_name, encrypted_phone, birth_date, gender,
                join_date, now_str, now_str, now_str, status, signup_type, role, membership
            ])

    # 3. 구독 및 사용량 데이터 생성
    print(" - 구독 및 월별 사용량 데이터 생성 중...")
    sub_id = 1
    
    with open(os.path.join(dir_path, 'subscription.csv'), 'w', newline='', encoding='utf-8') as f_sub, \
         open(os.path.join(dir_path, 'usage_monthly.csv'), 'w', newline='', encoding='utf-8') as f_usage:
         
        sub_writer = csv.writer(f_sub)
        sub_writer.writerow(['member_id', 'product_id', 'start_date', 'end_date', 'status', 'created_at', 'updated_at'])
        
        usage_writer = csv.writer(f_usage)
        usage_writer.writerow(['subscription_id', 'yyyymm', 'usage_details', 'created_at', 'updated_at'])
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        recent_months = get_last_12_months()
        
        for member_id, p_ids, start_date in subscriptions_to_create:
            start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
            start_ym = start_date.strftime('%Y%m')
            
            for p_id in p_ids:
                # 3-1. 구독 데이터 작성
                sub_writer.writerow([member_id, p_id, start_date_str, '', True, now_str, now_str])
                
                # 3-2. 사용량 데이터 작성 (ADDON은 제외)
                if p_id not in ADDON_IDS:
                    # 시작 월부터 이번 달까지의 월 목록 필터링
                    valid_months = [m for m in recent_months if m >= start_ym]
                    
                    for yyyymm in valid_months:
                        usage_details = {}
                        
                        if p_id in MOBILE_IDS:
                            # 1) 공통 모바일 사용량 (데이터, 음성, 문자)
                            usage_details = {
                                "data_gb": round(random.uniform(0.0, 150.0), 1),
                                "voice_min": random.randint(0, 500),
                                "sms_cnt": random.randint(0, 100)
                            }
                            
                            # 2) 테더링/쉐어링 제공 요금제인 경우에만 해당 항목 추가
                            if p_id in TETHERING_SUPPORTED_IDS:
                                usage_details["tethering_sharing_data_gb"] = round(random.uniform(0.0, 50.0), 1)
                                
                        elif p_id in TAB_WATCH_IDS:
                            usage_details = {"data_gb": round(random.uniform(0.5, 30.0), 1)}
                            if p_id == 52:
                                usage_details["voice_min"] = random.randint(0, 50)
                                usage_details["sms_cnt"] = random.randint(0, 250)
                            elif p_id == 59:
                                usage_details["voice_min"] = random.randint(0, 50)
                                usage_details["sms_cnt"] = random.randint(0, 500) # 무제한이므로 랜덤
                        elif p_id in IPTV_IDS:
                            usage_details = {
                                "viewing_hours": random.randint(10, 200),
                                "vod_purchases_cnt": random.randint(0, 10)
                            }
                        elif p_id in INTERNET_IDS:
                            usage_details = {
                                "total_data_gb": round(random.uniform(50.0, 1000.0), 1),
                                "qos_throttled_cnt": random.randint(0, 5)
                            }

                        usage_json = json.dumps(usage_details)
                        usage_writer.writerow([sub_id, yyyymm, usage_json, now_str, now_str])
                        
                sub_id += 1
                
    print(f"[{target_users}명] 데이터 생성 완료!\n")

if __name__ == "__main__":
    for size in SIZES:
        run_generation(size)
    print("모든 더미 데이터 생성이 완료되었습니다.")