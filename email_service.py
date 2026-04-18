import resend
import os
from datetime import datetime, timedelta

def load_resend_api_key():
    config_path = os.path.join(os.path.dirname(__file__), 'resend_config.txt')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None

resend.api_key = load_resend_api_key()

def load_email_sequence():
    seq_path = os.path.join(os.path.dirname(__file__), 'email_sequence.md')
    if not os.path.exists(seq_path):
        return ["Email 1 Placeholder", "Email 2 Placeholder", "Email 3 Placeholder"]
    
    with open(seq_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    parts = content.split('---')
    emails = []
    for p in parts:
        p = p.strip()
        if not p: continue
        # Extract title and body loosely
        lines = p.split('\n')
        subject = "DesGrow Automation"
        for l in lines:
            if l.startswith('**Chủ đề:**'):
                subject = l.replace('**Chủ đề:**', '').strip()
                break
        
        body_lines = [l for l in lines if not l.startswith('##') and not l.startswith('**Chủ đề:**') and not l.startswith('#')]
        body = '<br>'.join(body_lines).replace('\n', '')
        emails.append({'subject': subject, 'body': body})
    return emails

def send_waitlist_sequence(name, email):
    if not resend.api_key:
        print("Không tìm thấy API Key Resend")
        return

    emails = load_email_sequence()
    if len(emails) < 3:
        print("Không đủ 3 email trong file sequence.")
        return

    is_test = '+test' in email.lower()
    
    for idx, em in enumerate(emails[:3]):
        subject = em['subject']
        body = em['body'].replace('[Tên khách hàng]', name)
        
        # Sửa link thanh toán
        body = body.replace('[Link Trang Thanh Toán / Checkout của bạn]', 'https://homepower.vn#quick-pay')

        params = {
            "from": "DesGrow <onboarding@resend.dev>", # Default resend email for testing
            "to": [email],
            "subject": subject,
            "html": f"<p>{body}</p>"
        }
        
        # Lên lịch nếu không phải test
        if not is_test:
            if idx == 1:
                # Email 2: sau 2 ngày
                send_time = datetime.utcnow() + timedelta(days=2)
                params["scheduled_at"] = send_time.isoformat() + "Z"
            elif idx == 2:
                # Email 3: sau 3 ngày (1 ngày sau email 2)
                send_time = datetime.utcnow() + timedelta(days=3)
                params["scheduled_at"] = send_time.isoformat() + "Z"
        
        try:
            resend.Emails.send(params)
            print(f"Đã lên lịch hoặc gửi Email {idx+1} cho {email}")
        except Exception as e:
            print(f"Lỗi gửi email: {e}")

def send_order_confirmation(name, email, product_name, amount):
    if not resend.api_key: return
    
    subject = "🎉 Xác nhận đơn hàng DesGrow thành công!"
    body = f"""
    Chào {name},<br><br>
    Cảm ơn bạn đã tin tưởng và đặt hàng tại DesGrow.<br><br>
    <b>Thông tin đơn hàng:</b><br>
    - Sản phẩm: {product_name}<br>
    - Tổng thanh toán: {amount:,.0f}đ<br><br>
    Chuyên viên của chúng tôi sẽ liên hệ với bạn trong vòng 2 giờ làm việc để tiến hành cài đặt nền tảng trí tuệ nhân tạo cho shop của bạn.<br><br>
    Nếu có bất kỳ thắc mắc nào, hãy phản hồi lại email này nhé!<br><br>
    Trân trọng,<br>
    Đội ngũ DesGrow.
    """
    params = {
        "from": "DesGrow <onboarding@resend.dev>",
        "to": [email],
        "subject": subject,
        "html": f"<p>{body}</p>"
    }
    try:
        resend.Emails.send(params)
        print(f"Đã gửi email xác nhận đơn hàng cho {email}")
    except Exception as e:
        print(f"Lỗi gửi email xác nhận: {e}")
