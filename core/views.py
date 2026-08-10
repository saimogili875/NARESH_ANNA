from django.http import HttpResponse


def privacy_policy(request):
    html = """<!DOCTYPE html>
<html><head><title>Privacy Policy - Sri NRI Junior College</title>
<style>body{font-family:Arial,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.6;color:#333}h1{color:#1a237e}</style>
</head><body>
<h1>Privacy Policy</h1>
<p><strong>Sri NRI Junior College</strong> (operated by Sri Vigneswara Educational Society) uses the WhatsApp Business API to communicate with parents and guardians of enrolled students.</p>
<h2>Information We Collect</h2>
<p>We collect parent/guardian phone numbers provided during student admission for the sole purpose of sending attendance notifications and exam reminders.</p>
<h2>How We Use Your Information</h2>
<ul>
<li>Sending absence alerts when a student is marked absent</li>
<li>Sending weekly exam schedule reminders</li>
<li>Sending fee receipts</li>
</ul>
<h2>Data Sharing</h2>
<p>We do not sell or share your personal data with third parties. Messages are sent via the official Meta WhatsApp Business API.</p>
<h2>Data Retention</h2>
<p>Phone numbers are retained only while the student is enrolled at the college.</p>
<h2>Contact</h2>
<p>For questions about this policy, contact us at: Sri NRI Junior College, Guntur, Andhra Pradesh.</p>
<p><em>Last updated: August 2026</em></p>
</body></html>"""
    return HttpResponse(html)
