from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
import os


class Teacher(models.Model):
    name = models.CharField(max_length=200, verbose_name="Teacher Name")
    telegram_id = models.CharField(max_length=100, blank=True, verbose_name="Telegram Chat ID",
                                   help_text="Get your Chat ID from @userinfobot on Telegram")
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Teacher"
        verbose_name_plural = "Teachers"
        ordering = ['name']


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    streak = models.IntegerField(default=0)
    last_activity = models.DateField(null=True, blank=True)
    total_tests = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # ── Access Control ──────────────────────────────────────────────────────
    is_approved = models.BooleanField(default=False, verbose_name="Approved",
                                      help_text="Admin must approve before student can take tests")
    is_blocked = models.BooleanField(default=False, verbose_name="Blocked",
                                     help_text="Block student immediately")
    access_start = models.DateField(null=True, blank=True, verbose_name="Access Start Date",
                                    help_text="Set automatically when you approve the student")
    access_days = models.IntegerField(null=True, blank=True, verbose_name="Access Duration (days)",
                                      help_text="Days of unlimited access from approval. Leave blank for unlimited.")
    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}"

    def has_access(self):
        if self.is_blocked:
            return False, 'blocked'
        if not self.is_approved:
            return False, 'pending'
        if self.access_days and self.access_start:
            from datetime import timedelta
            expiry = self.access_start + timedelta(days=self.access_days)
            if timezone.now().date() > expiry:
                return False, 'expired'
        return True, 'ok'

    def expiry_date(self):
        if self.access_days and self.access_start:
            from datetime import timedelta
            return self.access_start + timedelta(days=self.access_days)
        return None

    def update_streak(self):
        today = timezone.now().date()
        if self.last_activity:
            delta = (today - self.last_activity).days
            if delta == 0:
                pass
            elif delta == 1:
                self.streak += 1
            else:
                self.streak = 1
        else:
            self.streak = 1
        self.last_activity = today
        self.save(update_fields=['streak', 'last_activity'])

    class Meta:
        verbose_name = "Student Profile"
        verbose_name_plural = "Student Profiles"


# ── Part 1.1 — Plain text questions (Q1–Q3) ───────────────────────────────────

class Part11Question(models.Model):
    """Part 1.1: plain text questions, no images. Q1–Q3."""
    question_number = models.IntegerField(verbose_name="Question #", help_text="e.g. 1, 2, 3")
    text = models.TextField(verbose_name="Question Text")
    prep_time_seconds = models.IntegerField(default=5, verbose_name="Prep Time (s)")
    answer_time_seconds = models.IntegerField(default=45, verbose_name="Answer Time (s)")
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"1.1 · Q{self.question_number}: {self.text[:70]}"

    class Meta:
        verbose_name = "Part 1.1 Question"
        verbose_name_plural = "Part 1.1 Questions"
        ordering = ['order', 'question_number']


# ── Part 1.2 — Image group questions (Q4–Q6) ─────────────────────────────────

class Part12Group(models.Model):
    """
    Part 1.2: one image shared across Q4, Q5, Q6.
    Create a group, upload one image, then add 3 sub-questions.
    """
    title = models.CharField(max_length=200, verbose_name="Group Title",
                              help_text="Internal label, e.g. 'City Life Photo Set A'")
    image = models.ImageField(upload_to='part12_images/', verbose_name="Shared Image",
                               help_text="Displayed for all questions in this group")
    context = models.TextField(blank=True, verbose_name="Image Context (read aloud)",
                                help_text="Optional: read to student before questions start")
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"Part 1.2 Group: {self.title}"

    class Meta:
        verbose_name = "Part 1.2 Question Group"
        verbose_name_plural = "Part 1.2 Question Groups"
        ordering = ['order']


class Part12Question(models.Model):
    """Sub-question inside a Part 1.2 group. Q4, Q5, or Q6."""
    group = models.ForeignKey(Part12Group, on_delete=models.CASCADE,
                               related_name='questions', verbose_name="Group")
    question_number = models.IntegerField(verbose_name="Question #", help_text="e.g. 4, 5, 6")
    text = models.TextField(verbose_name="Question Text")
    prep_time_seconds = models.IntegerField(default=5, verbose_name="Prep Time (s)")
    answer_time_seconds = models.IntegerField(default=45, verbose_name="Answer Time (s)")
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"1.2 · Q{self.question_number}: {self.text[:70]}"

    class Meta:
        verbose_name = "Part 1.2 Question"
        verbose_name_plural = "Part 1.2 Questions"
        ordering = ['order', 'question_number']


# ── Part 2 — Single image question (Q7) ──────────────────────────────────────

class Part2Question(models.Model):
    """Part 2: one image, student describes/responds. Q7."""
    question_number = models.IntegerField(default=7, verbose_name="Question #")
    text = models.TextField(verbose_name="Prompt / Task",
                             help_text="e.g. 'Describe what you see and explain what might be happening.'")
    image = models.ImageField(upload_to='part2_images/', verbose_name="Question Image")
    image_caption = models.CharField(max_length=300, blank=True, verbose_name="Caption (optional)")
    prep_time_seconds = models.IntegerField(default=30, verbose_name="Prep Time (s)")
    answer_time_seconds = models.IntegerField(default=120, verbose_name="Answer Time (s)")
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"Part 2 · Q{self.question_number}: {self.text[:70]}"

    class Meta:
        verbose_name = "Part 2 Question"
        verbose_name_plural = "Part 2 Questions"
        ordering = ['order', 'question_number']


# ── Part 3 — Image presentation question (Q8) ────────────────────────────────

class Part3Question(models.Model):
    """Part 3: image-based presentation with optional bullet points. Q8."""
    question_number = models.IntegerField(default=8, verbose_name="Question #")
    text = models.TextField(verbose_name="Task Description",
                             help_text="e.g. 'Present arguments for and against the topic shown.'")
    image = models.ImageField(upload_to='part3_images/', verbose_name="Question Image")
    image_caption = models.CharField(max_length=300, blank=True, verbose_name="Caption (optional)")
    bullet_points = models.TextField(
        blank=True,
        verbose_name="Bullet Points (optional)",
        help_text="Shown as on-screen hints. One per line:\n• Benefits for society\n• Economic impact\n• Your opinion"
    )
    prep_time_seconds = models.IntegerField(default=60, verbose_name="Prep Time (s)")
    answer_time_seconds = models.IntegerField(default=180, verbose_name="Answer Time (s)")
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    def get_bullet_list(self):
        if not self.bullet_points:
            return []
        return [l.strip() for l in self.bullet_points.strip().splitlines() if l.strip()]

    def __str__(self):
        return f"Part 3 · Q{self.question_number}: {self.text[:70]}"

    class Meta:
        verbose_name = "Part 3 Question"
        verbose_name_plural = "Part 3 Questions"
        ordering = ['order', 'question_number']


# ── Mock Test / Outsider ──────────────────────────────────────────────────────

class MockTest(models.Model):
    PART_CHOICES = [('1.1','Part 1.1'),('1.2','Part 1.2'),('2','Part 2'),('3','Part 3'),('full','Full Test')]
    code = models.CharField(max_length=20, unique=True, verbose_name="Access Code")
    title = models.CharField(max_length=200, verbose_name="Test Title")
    part = models.CharField(max_length=10, choices=PART_CHOICES, verbose_name="Test Part")
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True,
                                help_text="Results sent to this teacher via Telegram")
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True, help_text="Leave blank for no expiry")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.title} [{self.code}] — Part {self.part}"

    def is_valid(self):
        if not self.is_active:
            return False
        if self.valid_until and timezone.now() > self.valid_until:
            return False
        return True

    class Meta:
        verbose_name = "Mock Test"
        verbose_name_plural = "Mock Tests"
        ordering = ['-created_at']


class Candidate(models.Model):
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='candidates')
    candidate_id = models.CharField(max_length=50, verbose_name="Candidate ID",
                                     help_text="ID given to the candidate, e.g. CAND001")
    full_name = models.CharField(max_length=200)
    has_taken_test = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.candidate_id}) — {self.mock_test.code}"

    class Meta:
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"
        unique_together = [('mock_test', 'candidate_id')]


# ── Test Session ──────────────────────────────────────────────────────────────

class TestSession(models.Model):
    SESSION_TYPE_CHOICES = [('center','Center Student'),('outsider','External Candidate')]
    STATUS_CHOICES = [('started','Started'),('in_progress','In Progress'),
                      ('completed','Completed'),('abandoned','Abandoned')]
    PART_CHOICES = [('1.1','Part 1.1'),('1.2','Part 1.2'),('2','Part 2'),('3','Part 3'),('full','Full Test')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES)
    part = models.CharField(max_length=10, choices=PART_CHOICES)

    student = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='test_sessions')
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True)
    candidate = models.ForeignKey(Candidate, on_delete=models.SET_NULL, null=True, blank=True)
    mock_test = models.ForeignKey(MockTest, on_delete=models.SET_NULL, null=True, blank=True)
    # For outsiders who self-identify (no pre-registration)
    outsider_candidate_id = models.CharField(max_length=100, blank=True)

    full_name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='started')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_score = models.FloatField(null=True, blank=True)
    rating_score = models.IntegerField(null=True, blank=True,
                                        help_text="Official rating score converted from raw score")
    telegram_sent = models.BooleanField(default=False)

    # ── Audio auto-cleanup ────────────────────────────────────────────────────
    audio_deleted = models.BooleanField(default=False)
    audio_delete_after = models.DateTimeField(
        null=True, blank=True,
        help_text="Auto-set to 2 days after completion. Cron/management command deletes files after this."
    )

    def __str__(self):
        return f"{self.full_name} — Part {self.part} ({self.started_at.strftime('%Y-%m-%d')})"

    class Meta:
        verbose_name = "Test Session"
        verbose_name_plural = "Test Sessions"
        ordering = ['-started_at']


class QuestionResponse(models.Model):
    session = models.ForeignKey(TestSession, on_delete=models.CASCADE, related_name='responses')
    question_number = models.IntegerField()

    # Snapshot of which question was asked (one will be set)
    part11_question = models.ForeignKey(Part11Question, on_delete=models.SET_NULL, null=True, blank=True)
    part12_question = models.ForeignKey(Part12Question, on_delete=models.SET_NULL, null=True, blank=True)
    part2_question  = models.ForeignKey(Part2Question,  on_delete=models.SET_NULL, null=True, blank=True)
    part3_question  = models.ForeignKey(Part3Question,  on_delete=models.SET_NULL, null=True, blank=True)
    question_text = models.TextField(blank=True)  # saved at response time

    audio_file = models.FileField(upload_to='recordings/%Y/%m/', null=True, blank=True)
    transcription = models.TextField(blank=True)
    score = models.FloatField(null=True, blank=True)
    score_breakdown = models.JSONField(default=dict, blank=True)
    feedback = models.TextField(blank=True)
    answered_at = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.FloatField(null=True, blank=True)

    def delete_audio(self):
        """Remove audio file from disk and clear field."""
        if self.audio_file:
            try:
                path = self.audio_file.path
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            self.audio_file = None
            self.save(update_fields=['audio_file'])

    def __str__(self):
        return f"Q{self.question_number} — {self.session.full_name}"

    class Meta:
        verbose_name = "Question Response"
        verbose_name_plural = "Question Responses"
        ordering = ['question_number']


class SiteAnalytics(models.Model):
    date = models.DateField(unique=True)
    total_students = models.IntegerField(default=0)
    new_students = models.IntegerField(default=0)
    total_tests = models.IntegerField(default=0)
    total_outsider_tests = models.IntegerField(default=0)
    avg_score = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Site Analytics"
        verbose_name_plural = "Site Analytics"
        ordering = ['-date']


# ── Announcements / News Banners ──────────────────────────────────────────────

class Announcement(models.Model):
    """News / ad banners shown to students on dashboard. Admin controls on/off."""
    STYLE_CHOICES = [
        ('info',    'Info (blue)'),
        ('success', 'Success (green)'),
        ('warning', 'Warning (yellow)'),
        ('promo',   'Promo (purple)'),
    ]
    title     = models.CharField(max_length=200)
    body      = models.TextField(help_text="Supports basic HTML (bold, links).")
    style     = models.CharField(max_length=20, choices=STYLE_CHOICES, default='info')
    emoji     = models.CharField(max_length=10, default='📢', blank=True)
    is_active = models.BooleanField(default=True, verbose_name="Show to students")
    show_once = models.BooleanField(
        default=False,
        help_text="If on, each student sees it only once and can dismiss it."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{'✅' if self.is_active else '⏸'} {self.title}"

    class Meta:
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"
        ordering = ['-created_at']


class AnnouncementDismissal(models.Model):
    """Tracks which students dismissed a show_once announcement."""
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE,
                                      related_name='dismissals')
    user         = models.ForeignKey(User, on_delete=models.CASCADE)
    dismissed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('announcement', 'user')]
        verbose_name = "Announcement Dismissal"
