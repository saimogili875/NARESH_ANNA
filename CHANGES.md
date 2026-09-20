# Changes & System Fixes Log — Sri NRI Junior College

This document details all technical fixes, security hardening, UI enhancements, and structural improvements implemented across the 9 tasks.

---

## 1. Media & Image Serving Fixes (`DEBUG=False` Production Readiness)
- **Production Media Route**: Replaced Django's `static()` helper in `core/urls.py` with `re_path(r'^media/(?P<path>.*)$', django.views.static.serve, {'document_root': settings.MEDIA_ROOT})` so `/media/` works seamlessly when `DEBUG=False`.
- **Railway Volume Persistence**: Configured `MEDIA_ROOT` in `core/settings.py` to check `os.environ.get('MEDIA_ROOT', BASE_DIR / 'media')`.
- **Avatar Fallback System**: Created a reusable template snippet `templates/_avatar.html` that renders student photos with `loading="lazy" decoding="async"` and falls back to circular initials on missing images or `onerror` events.
- **Landing Page Image Optimization**: Built and executed `scripts/optimize_images.py` (Pillow) to compress `static/images/toppers/*.jpg` from 14 MB to ~60 KB each (>99% size reduction).

---

## 2. Theme & Golden Light Cleanup
- **Removed Gold Border System**: Removed `@property --gold-angle`, `@keyframes rotateGoldBorder`, `::before` conic-gradient rules, `.gold-pulse-active`, and click handler JS from `templates/base.html`, `templates/accounts/groups.html`, and `templates/marks/exam_list.html`.
- **Subtle Modern Theme**: Replaced glowing outlines with subtle neutral borders (`1px solid var(--sf-border)`), preserving brand accents (`--sf-gold: #C5A059`) without glowing animations.

---

## 3. Responsive UI & Fluid Typography
- **Google Fonts Integration**: Added Inter (sans-serif) and JetBrains Mono (monospace) in `templates/base.html`.
- **Fluid Type Scale**: Configured `clamp()` type scaling for body text, headings, tabular numeric data, and table rows. Set minimum 16px input font size on touch devices to prevent mobile iOS zoom.
- **Mobile Drawer Sidebar Navigation**: Built off-canvas mobile drawer navigation for `#sidebar` on screens `< 992px` with topbar hamburger button, dark backdrop overlay, and keyboard `Esc` dismissal.

---

## 4. Academic Structure & Group Deletion Fix
- **Atomic Batch Deletion**: Refactored `group_delete` and `section_delete` in `accounts/views.py` to require `POST` with CSRF, wrapped inside `transaction.atomic()`. Deletes related records (`PendingMessage`, `Mark`, `MarkTotal`, `Attendance`, `FeePayment`, `StudentFee`, `Student`, `Section`, `Group`) in batch.
- **Delete Confirmation Modals**: Updated `templates/accounts/groups.html` with POST confirmation modals detailing student and record counts.
- **Unit Testing**: Added `GroupDeleteTestCase` in `accounts/tests.py`.

---

## 5. Attendance Search & Quick Filter Chips
- **Live Search & Filter Chips**: Added debounced search bar and quick-filter chips (All, Present, Absent) with live counts to `templates/attendance/list.html`.
- **Keyboard Shortcut**: Keyboard `/` focuses the search bar instantly.
- **Mobile Sticky Action Bar**: Added fixed bottom action bar for touch screens.

---

## 6. Marks Page Category Filter
- **Category Seeding**: Created management command `seed_exam_categories` to seed standard categories (JEE-MAIN, IPE-MEC, IPE-CEC, IPE-MPC, NEET, IPE-BPC).
- **Default Empty State & Filter**: Updated `marks/views.py::exam_list` and `templates/marks/exam_list.html` so the page starts empty and displays exams only when a category is selected (`?category=<id>`).
- **POST Exam Deletion**: Converted exam deletion to POST with CSRF and confirmation modal.

---

## 7. Total Marks Column & Dual Entry Mode
- **`MarkTotal` Model**: Added `MarkTotal` model storing `student`, `exam`, `total_obtained`, `source` (`auto` vs `manual`), and `updated_at`.
- **Dual Entry Calculation**: `marks_entry` in `marks/views.py` auto-calculates total from subject marks (`source='auto'`) or accepts direct manual total inputs (`source='manual'`), displaying discrepancy warning badges if they differ.
- **PDF & Report Integration**: Updated `templates/marks/entry.html` and export PDF generators to display Total Marks and percentages.
- **Unit Testing**: Added `MarkTotalTestCase` in `marks/tests.py`.

---

## 8. Fee Management Search & % Paid Column
- **Prominent Search Bar**: Replaced search input with prominent debounced search bar in `templates/fees/list.html`.
- **"% Paid" Progress Column**: Added **"% Paid"** column with progress bars and color coding (gray 0%, red <50%, amber 50-99%, green 100%).

---

## 9. Security Hygiene & System Modernization
- **Hardcoded Credential Cleanup**: Removed plain-text superuser passwords from `build.sh`. Superusers are now created dynamically from `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_PASSWORD` environment variables.
- **Django 5.1+ Storage Configuration**: Replaced deprecated `STATICFILES_STORAGE` in `core/settings.py` with Django 5.1+ `STORAGES` dictionary (`whitenoise.storage.CompressedStaticFilesStorage`).

---

## Instructions for Deploying

1. **Rotate Production Superuser Passwords**:
   On your live server / Railway app, log in to the Django Admin panel or shell and update your superuser passwords.

2. **Mount Railway Volume for Media**:
   - In Railway, add a Volume mounted at `/data` to your service.
   - Set environment variable: `MEDIA_ROOT=/data/media`
   - Untrack git media cache: `git rm -r --cached media` (without deleting local files).

3. **Deploy**:
   Commit and push your branch:
   ```bash
   git add -A
   git commit -m "UI fixes, responsive drawer, group deletion, marks total & fee search"
   git push origin ui-fixes-oct
   ```
