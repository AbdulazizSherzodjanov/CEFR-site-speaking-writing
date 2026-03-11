import json
import random
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Avg, Count

from .models import (
    Teacher, StudentProfile,
    Part11Question, Part12Group, Part12Question,
    Part2Question, Part3Question,
    MockTest, Candidate, TestSession, QuestionResponse
)
from .services import transcribe_audio, score_response, send_telegram_results, raw_to_rating
from .middleware import get_online_count
from .forms import RegisterForm

logger = logging.getLogger(__name__)

PART_INSTRUCTIONS = {
    '1.1': (
        "Welcome to Part 1.1. You will hear three questions one by one. "
        "For each question you have a short preparation time, then a bell sounds — start speaking. "
        "A second bell ends your answer time. Answer as fully and naturally as you can."
    ),
    '1.2': (
        "Welcome to Part 1.2. An image will be shown on screen. "
        "Three questions about this image will follow one by one. "
        "Look at the image carefully. When the bell rings, begin your answer."
    ),
    '2': (
        "Welcome to Part 2. You will see an image with a task. "
        "Use the preparation time to plan your response. "
        "When the bell sounds, speak clearly and in detail. "
        "A second bell will end your speaking time."
    ),
    '3': (
        "Welcome to Part 3. You will be given a topic and an image with bullet points. "
        "Use the preparation time to plan a structured presentation. "
        "Consider all the points shown. Present both sides of the topic. "
        "The first bell means start; the second means stop."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Question picker  — RANDOM selection per part
# ─────────────────────────────────────────────────────────────────────────────

def _pick_questions(part_str, count=None):
    """
    Return a list of question dicts for the given part, randomly selected.
    count=None means "all" (used for Full Test where we want exactly 1 per slot).
    """
    questions = []

    if part_str == '1.1':
        pool = list(Part11Question.objects.filter(is_active=True))
        n = count if count else 3
        chosen = random.sample(pool, min(n, len(pool))) if pool else []
        for i, q in enumerate(chosen, 1):
            questions.append({
                'type': '1.1', 'id': q.id,
                'number': i, 'text': q.text,
                'image_url': None, 'group_image_url': None,
                'group_context': '', 'image_caption': '',
                'bullets': [],
                'prep': q.prep_time_seconds, 'answer': q.answer_time_seconds,
            })

    elif part_str == '1.2':
        # Pick one random active group, then 3 random questions from it
        groups = list(Part12Group.objects.filter(is_active=True))
        if groups:
            group = random.choice(groups)
            pool  = list(group.questions.filter(is_active=True))
            n     = count if count else 3
            chosen = random.sample(pool, min(n, len(pool))) if pool else []
            for i, q in enumerate(chosen, 4):  # Q4, Q5, Q6
                questions.append({
                    'type': '1.2', 'id': q.id,
                    'number': i, 'text': q.text,
                    'image_url': None,
                    'group_image_url': group.image.url if group.image else None,
                    'group_context': group.context or '',
                    'image_caption': '',
                    'bullets': [],
                    'prep': q.prep_time_seconds, 'answer': q.answer_time_seconds,
                })

    elif part_str == '2':
        pool = list(Part2Question.objects.filter(is_active=True))
        n = count if count else 1
        chosen = random.sample(pool, min(n, len(pool))) if pool else []
        for q in chosen:
            questions.append({
                'type': '2', 'id': q.id,
                'number': 7, 'text': q.text,
                'image_url': q.image.url if q.image else None,
                'group_image_url': None,
                'group_context': '', 'image_caption': q.image_caption or '',
                'bullets': [],
                'prep': q.prep_time_seconds, 'answer': q.answer_time_seconds,
            })

    elif part_str == '3':
        pool = list(Part3Question.objects.filter(is_active=True))
        n = count if count else 1
        chosen = random.sample(pool, min(n, len(pool))) if pool else []
        for q in chosen:
            questions.append({
                'type': '3', 'id': q.id,
                'number': 8, 'text': q.text,
                'image_url': q.image.url if q.image else None,
                'group_image_url': None,
                'group_context': '', 'image_caption': q.image_caption or '',
                'bullets': q.get_bullet_list(),
                'prep': q.prep_time_seconds, 'answer': q.answer_time_seconds,
            })

    return questions


def _pick_full_test_questions():
    """
    Full test: random 3 from 1.1 + random group + 3 Qs from 1.2 + 1 from 2 + 1 from 3.
    Re-number sequentially 1→8.
    """
    all_q = (
        _pick_questions('1.1', 3)
        + _pick_questions('1.2', 3)
        + _pick_questions('2', 1)
        + _pick_questions('3', 1)
    )
    for i, q in enumerate(all_q, 1):
        q['number'] = i
    return all_q


# ─────────────────────────────────────────────────────────────────────────────
# Public views
# ─────────────────────────────────────────────────────────────────────────────

def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'speaking_test/home.html', {'live_count': get_online_count()})


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user    = form.save(commit=False)
            user.is_active = True  # Can log in but access controlled by is_approved
            user.save()
            teacher = form.cleaned_data.get('teacher')
            StudentProfile.objects.create(user=user, teacher=teacher, is_approved=False)
            return redirect('register_pending')
    else:
        form = RegisterForm()
    return render(request, 'speaking_test/register.html', {
        'form': form,
        'teachers': Teacher.objects.filter(is_active=True),
    })


def register_pending(request):
    return render(request, 'speaking_test/register_pending.html')


def outsider_entry(request):
    """
    Outsiders enter: test code + full name + any candidate ID.
    No pre-registration required.
    """
    if request.method == 'POST':
        code         = request.POST.get('code', '').strip().upper()
        candidate_id = request.POST.get('candidate_id', '').strip()
        full_name    = request.POST.get('full_name', '').strip()

        if not candidate_id:
            messages.error(request, "Please enter a Candidate ID.")
            return render(request, 'speaking_test/outsider_entry.html')
        if not full_name:
            messages.error(request, "Please enter your full name.")
            return render(request, 'speaking_test/outsider_entry.html')

        mock_test = MockTest.objects.filter(code=code).first()
        if not mock_test:
            messages.error(request, "Invalid test code. Please check and try again.")
            return render(request, 'speaking_test/outsider_entry.html')
        if not mock_test.is_valid():
            messages.error(request, "This test has expired or is no longer active.")
            return render(request, 'speaking_test/outsider_entry.html')

        # Log out any logged-in center student silently
        if request.user.is_authenticated:
            logout(request)

        # Store in session — no DB candidate lookup needed
        request.session['outsider_mock_test_id'] = mock_test.id
        request.session['outsider_candidate_id'] = candidate_id
        request.session['outsider_full_name']     = full_name
        request.session['is_outsider']            = True
        request.session.modified = True

        return redirect('test_start_part', part=mock_test.part)

    return render(request, 'speaking_test/outsider_entry.html')


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)
    sessions   = TestSession.objects.filter(
        student=request.user, status='completed'
    ).order_by('-started_at')[:10]
    all_sessions = TestSession.objects.filter(student=request.user, status='completed')
    avg_score    = all_sessions.aggregate(avg=Avg('total_score'))['avg']
    total_tests  = all_sessions.count()
    part_stats   = list(all_sessions.values('part').annotate(
        avg=Avg('total_score'), count=Count('id')
    ))
    profile.update_streak()
    profile.total_tests = total_tests
    profile.save(update_fields=['total_tests'])

    PART_CARDS = [
        {'part':'1.1','label':'Part 1.1','desc':'3 text questions','icon':'💬','level':'A1–A2'},
        {'part':'1.2','label':'Part 1.2','desc':'Image group questions','icon':'🖼️','level':'A2–B1'},
        {'part':'2',  'label':'Part 2',  'desc':'Image description','icon':'📸','level':'B1–B2'},
        {'part':'3',  'label':'Part 3',  'desc':'Image presentation','icon':'🎤','level':'B2–C1'},
        {'part':'full','label':'Full Test','desc':'All parts (8 questions)','icon':'🏆','level':'A1–C1'},
    ]

    # Announcements – active, excluding dismissed show_once ones
    from .models import Announcement, AnnouncementDismissal
    dismissed_ids = list(AnnouncementDismissal.objects.filter(
        user=request.user
    ).values_list('announcement_id', flat=True))
    announcements = list(Announcement.objects.filter(is_active=True).exclude(
        id__in=[aid for aid in dismissed_ids]
    ))
    # Further filter: if show_once and dismissed, remove
    announcements = [a for a in announcements
                     if not (a.show_once and a.id in dismissed_ids)]

    has_acc, acc_reason = profile.has_access() if not request.user.is_staff else (True, 'ok')

    return render(request, 'speaking_test/dashboard.html', {
        'profile': profile, 'sessions': sessions,
        'avg_score': round(avg_score, 2) if avg_score else None,
        'total_tests': total_tests, 'part_stats': part_stats,
        'live_count': get_online_count(), 'parts': PART_CARDS,
        'announcements': announcements,
        'has_access': has_acc, 'access_reason': acc_reason,
    })


@login_required
def test_select(request):
    PART_CARDS = [
        {'part':'1.1','label':'Part 1.1','desc':'3 text questions (A1–A2)','icon':'💬','time':'45s each'},
        {'part':'1.2','label':'Part 1.2','desc':'Image group questions (A2–B1)','icon':'🖼️','time':'45s each'},
        {'part':'2',  'label':'Part 2',  'desc':'Describe an image (B1–B2)','icon':'📸','time':'2 min'},
        {'part':'3',  'label':'Part 3',  'desc':'Image presentation (B2–C1)','icon':'🎤','time':'3 min'},
        {'part':'full','label':'Full Test','desc':'All 4 parts • 8 questions (A1–C1)','icon':'🏆','time':'~15 min'},
    ]
    return render(request, 'speaking_test/test_select.html', {
        'parts': PART_CARDS, 'is_outsider': False,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Start test
# ─────────────────────────────────────────────────────────────────────────────

def test_start_part(request, part):
    if part not in ('1.1', '1.2', '2', '3', 'full'):
        return redirect('home')

    is_outsider = request.session.get('is_outsider', False)

    if is_outsider:
        mock_test_id = request.session.get('outsider_mock_test_id')
        candidate_id = request.session.get('outsider_candidate_id', '')
        full_name    = request.session.get('outsider_full_name', 'Candidate')

        if not mock_test_id:
            messages.error(request, "Session expired. Please re-enter your test code.")
            return redirect('outsider_entry')

        mock_test = MockTest.objects.filter(id=mock_test_id).first()
        if not mock_test or not mock_test.is_valid():
            messages.error(request, "Test not found or expired.")
            return redirect('outsider_entry')

        session = TestSession.objects.create(
            session_type='outsider',
            part=part,
            mock_test=mock_test,
            teacher=mock_test.teacher,
            full_name=full_name,
            outsider_candidate_id=candidate_id,
            status='started',
        )

    elif request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            # Staff/admin bypass access control
            profile = getattr(request.user, 'student_profile', None)
            session = TestSession.objects.create(
                session_type='center', part=part,
                student=request.user,
                teacher=profile.teacher if profile else None,
                full_name=request.user.get_full_name() or request.user.username,
                status='started',
            )
        else:
            profile, _ = StudentProfile.objects.get_or_create(user=request.user)
            can, reason = profile.has_access()
            if not can:
                return redirect('access_denied', reason=reason)
            session = TestSession.objects.create(
                session_type='center', part=part,
                student=request.user,
                teacher=profile.teacher if profile else None,
                full_name=request.user.get_full_name() or request.user.username,
                status='started',
            )
    else:
        return redirect('home')

    return redirect('test_session', session_id=session.id)


# ─────────────────────────────────────────────────────────────────────────────
# Test session
# ─────────────────────────────────────────────────────────────────────────────

def test_session(request, session_id):
    session = get_object_or_404(TestSession, id=session_id)

    # Security
    if not request.session.get('is_outsider') and request.user.is_authenticated:
        if session.student_id and session.student != request.user:
            return redirect('dashboard')

    part = session.part
    if part == 'full':
        questions    = _pick_full_test_questions()
        instructions = (
            "Welcome to the Full Speaking Test. You will complete all 4 parts: "
            "Part 1.1 (text questions), Part 1.2 (image group), "
            "Part 2 (image description), and Part 3 (presentation). "
            "Questions are given one by one. Listen carefully, prepare, then speak when the bell rings."
        )
    else:
        questions    = _pick_questions(part)
        instructions = PART_INSTRUCTIONS.get(part, "Listen carefully and answer each question.")

    return render(request, 'speaking_test/test_session.html', {
        'session': session,
        'questions_json': json.dumps(questions),
        'instructions': instructions,
        'part': part,
        'part_label': 'Full Test' if part == 'full' else f'Part {part}',
        # Center students see score after each question; outsiders just move on
        'show_scores': 'true' if session.session_type == 'center' else 'false',
    })


# ─────────────────────────────────────────────────────────────────────────────
# API: submit one question's audio
# ─────────────────────────────────────────────────────────────────────────────

@require_POST
def api_submit_response(request):
    try:
        session_id  = request.POST.get('session_id')
        question_id = request.POST.get('question_id')
        q_number    = int(request.POST.get('question_number', 1))
        q_text      = request.POST.get('question_text', '')
        q_type      = request.POST.get('question_type', '1.1')
        audio_file  = request.FILES.get('audio')
        duration    = float(request.POST.get('duration', 0))

        session = get_object_or_404(TestSession, id=session_id)
        session.status = 'in_progress'
        session.save(update_fields=['status'])

        resp = QuestionResponse(
            session=session, question_number=q_number,
            question_text=q_text, duration_seconds=duration,
        )
        if q_type == '1.1':
            resp.part11_question_id = question_id
        elif q_type == '1.2':
            resp.part12_question_id = question_id
        elif q_type == '2':
            resp.part2_question_id  = question_id
        elif q_type == '3':
            resp.part3_question_id  = question_id

        if audio_file:
            resp.audio_file.save(f'{session_id}_q{q_number}.webm', audio_file, save=False)
            resp.save()
            transcription = transcribe_audio(resp.audio_file.path)
            resp.transcription = transcription
            score_data = score_response(transcription, q_text, q_type)
            resp.score          = score_data.get('score')
            resp.score_breakdown = score_data
            resp.feedback       = score_data.get('feedback', '')
            resp.save()
        else:
            resp.save()

        return JsonResponse({
            'success': True, 'response_id': resp.id,
            'transcription': resp.transcription,
            'score': resp.score,
            'score_breakdown': resp.score_breakdown,
            'feedback': resp.feedback,
        })
    except Exception as e:
        logger.error(f"api_submit_response: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# Complete + Results
# ─────────────────────────────────────────────────────────────────────────────

def test_complete(request, session_id):
    session = get_object_or_404(TestSession, id=session_id)
    scores  = [r.score for r in session.responses.all() if r.score is not None]
    if scores:
        raw = round(sum(scores) / len(scores), 1)
        session.total_score  = raw
        session.rating_score = raw_to_rating(raw)
    session.status       = 'completed'
    session.completed_at = timezone.now()
    session.audio_delete_after = timezone.now() + timezone.timedelta(days=2)
    session.save()

    if session.student:
        try:
            p = session.student.student_profile
            p.total_tests += 1
            p.save(update_fields=['total_tests'])
        except Exception:
            pass

    # Clear outsider session
    if session.session_type == 'outsider':
        for k in ('is_outsider', 'outsider_mock_test_id', 'outsider_candidate_id', 'outsider_full_name'):
            request.session.pop(k, None)

    send_telegram_results(session)
    return redirect('test_results', session_id=session_id)


def test_results(request, session_id):
    session   = get_object_or_404(TestSession, id=session_id)
    responses = session.responses.order_by('question_number')

    # Only center students see the full results page.
    # Outsiders see a simple "thank you" page.
    if session.session_type == 'outsider':
        return render(request, 'speaking_test/test_done_outsider.html', {'session': session})

    return render(request, 'speaking_test/test_results.html', {
        'session': session, 'responses': responses,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Misc API
# ─────────────────────────────────────────────────────────────────────────────

def writing_check(request):
    """Writing exam checker — rule-based band estimator for teachers."""
    return render(request, 'speaking_test/writing_check.html')


def api_session_status(request, session_id):
    s = get_object_or_404(TestSession, id=session_id)
    return JsonResponse({'status': s.status, 'total_score': s.total_score})

def api_live_count(request):
    return JsonResponse({'count': get_online_count()})


# ═══════════════════════════════════════════════════════════════════════════
#  LEADERBOARD
# ═══════════════════════════════════════════════════════════════════════════

def leaderboard(request):
    """Top students by average score and streak. Excludes staff/superusers."""
    from django.db.models import Avg, Count
    from .models import TestSession, StudentProfile

    # Top by average score — exclude staff and superusers
    top_score = (
        TestSession.objects
        .filter(
            status='completed', session_type='center', total_score__isnull=False,
            student__is_staff=False, student__is_superuser=False
        )
        .values('student__id', 'student__first_name', 'student__last_name', 'student__username')
        .annotate(avg=Avg('total_score'), tests=Count('id'))
        .filter(tests__gte=1)
        .order_by('-avg')[:20]
    )

    # Top by streak — exclude staff and superusers
    top_streak = (
        StudentProfile.objects
        .select_related('user')
        .filter(streak__gt=0, user__is_staff=False, user__is_superuser=False)
        .order_by('-streak')[:20]
    )

    # Current user's rank (only if not staff)
    my_rank = None
    if request.user.is_authenticated and not request.user.is_staff:
        my_avg = (
            TestSession.objects
            .filter(student=request.user, status='completed', total_score__isnull=False)
            .aggregate(avg=Avg('total_score'))['avg']
        )
        if my_avg:
            better = (
                TestSession.objects
                .filter(
                    status='completed', session_type='center', total_score__isnull=False,
                    student__is_staff=False, student__is_superuser=False
                )
                .values('student__id')
                .annotate(avg=Avg('total_score'))
                .filter(avg__gt=my_avg)
                .count()
            )
            my_rank = better + 1

    return render(request, 'speaking_test/leaderboard.html', {
        'top_score':  list(top_score),
        'top_streak': top_streak,
        'my_rank':    my_rank,
    })


# ═══════════════════════════════════════════════════════════════════════════
#  STUDENT PROGRESS
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def student_progress(request):
    """Detailed progress page for the logged-in student."""
    from django.db.models import Avg, Count
    sessions = (
        TestSession.objects
        .filter(student=request.user, status='completed')
        .order_by('started_at')
        .prefetch_related('responses')
    )
    # Build chart data: last 30 sessions
    chart_labels, chart_scores = [], []
    for s in sessions.order_by('-started_at')[:30]:
        chart_labels.append(s.started_at.strftime('%b %d'))
        chart_scores.append(round(s.total_score, 2) if s.total_score else 0)
    chart_labels.reverse(); chart_scores.reverse()

    # Per-part averages
    part_avgs = (
        sessions.values('part')
        .annotate(avg=Avg('total_score'), cnt=Count('id'))
        .order_by('part')
    )
    PART_LABELS = {'1.1':'Part 1.1','1.2':'Part 1.2','2':'Part 2','3':'Part 3','full':'Full Test'}
    part_avgs_labeled = [
        {'part': PART_LABELS.get(r['part'], r['part']), 'avg': round(r['avg'],2) if r['avg'] else 0, 'cnt': r['cnt']}
        for r in part_avgs
    ]

    # Best / worst scores
    best  = sessions.filter(total_score__isnull=False).order_by('-total_score').first()
    worst = sessions.filter(total_score__isnull=False).order_by('total_score').first()

    try:
        profile = request.user.student_profile
    except Exception:
        profile = None

    overall_avg = sessions.aggregate(avg=Avg('total_score'))['avg']
    total = sessions.count()

    return render(request, 'speaking_test/student_progress.html', {
        'sessions':          sessions.order_by('-started_at')[:50],
        'chart_labels':      chart_labels,
        'chart_scores':      chart_scores,
        'part_avgs':         part_avgs_labeled,
        'best':              best,
        'worst':             worst,
        'profile':           profile,
        'overall_avg':       round(overall_avg, 2) if overall_avg else None,
        'total_tests':       total,
    })


# ═══════════════════════════════════════════════════════════════════════════
#  TEACHER PANEL
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def teacher_panel(request):
    """
    Teacher-facing panel. Accessible if the logged-in user's student profile
    has teacher privileges, OR if the user is staff.
    We attach a teacher by checking if any Teacher.email matches user.email.
    """
    from django.db.models import Avg, Count
    from .models import Teacher, TestSession, StudentProfile

    # Resolve which teacher this user is
    teacher = Teacher.objects.filter(email=request.user.email).first()
    if not teacher and not request.user.is_staff:
        from django.contrib import messages as msgs
        msgs.error(request, "You don't have teacher access.")
        return redirect('dashboard')

    # Students under this teacher
    if teacher:
        student_profiles = StudentProfile.objects.filter(teacher=teacher).select_related('user')
        sessions_qs = TestSession.objects.filter(teacher=teacher)
    else:  # staff sees all
        student_profiles = StudentProfile.objects.all().select_related('user')
        sessions_qs = TestSession.objects.all()

    # Filter
    part_filter = request.GET.get('part', '')
    search      = request.GET.get('q', '').strip()
    if part_filter:
        sessions_qs = sessions_qs.filter(part=part_filter)
    if search:
        sessions_qs = sessions_qs.filter(full_name__icontains=search)

    sessions_qs = sessions_qs.filter(status='completed').order_by('-started_at')

    # Per-student stats
    student_stats = []
    for sp in student_profiles:
        sts = sessions_qs.filter(student=sp.user)
        agg = sts.aggregate(avg=Avg('total_score'), cnt=Count('id'))
        student_stats.append({
            'profile': sp,
            'avg':  round(agg['avg'], 2) if agg['avg'] else None,
            'cnt':  agg['cnt'],
            'streak': sp.streak,
            'last': sp.last_activity,
        })
    student_stats.sort(key=lambda x: x['avg'] or 0, reverse=True)

    # Overall stats
    overall = sessions_qs.aggregate(avg=Avg('total_score'), total=Count('id'))
    part_breakdown = (
        sessions_qs.values('part')
        .annotate(avg=Avg('total_score'), cnt=Count('id'))
        .order_by('part')
    )

    return render(request, 'speaking_test/teacher_panel.html', {
        'teacher':        teacher,
        'student_stats':  student_stats,
        'sessions':       sessions_qs[:100],
        'overall_avg':    round(overall['avg'], 2) if overall['avg'] else None,
        'total_sessions': overall['total'],
        'part_breakdown': list(part_breakdown),
        'part_filter':    part_filter,
        'search':         search,
        'student_count':  len(student_stats),
    })


# ═══════════════════════════════════════════════════════════════════════════
#  ADMIN ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def admin_analytics(request):
    """Site-wide analytics. Staff only."""
    if not request.user.is_staff:
        return redirect('dashboard')

    from django.db.models import Avg, Count
    from django.db.models.functions import TruncDate, TruncWeek
    from .models import TestSession, StudentProfile, Teacher

    # Totals
    total_students  = StudentProfile.objects.count()
    total_sessions  = TestSession.objects.filter(status='completed').count()
    total_outsiders = TestSession.objects.filter(status='completed', session_type='outsider').count()
    total_center    = TestSession.objects.filter(status='completed', session_type='center').count()
    overall_avg     = TestSession.objects.filter(status='completed', total_score__isnull=False).aggregate(avg=Avg('total_score'))['avg']
    total_teachers  = Teacher.objects.filter(is_active=True).count()

    # Sessions per day (last 30 days)
    from django.utils import timezone as tz
    cutoff = tz.now() - tz.timedelta(days=30)
    daily = (
        TestSession.objects
        .filter(status='completed', started_at__gte=cutoff)
        .annotate(day=TruncDate('started_at'))
        .values('day')
        .annotate(cnt=Count('id'), avg=Avg('total_score'))
        .order_by('day')
    )
    daily_labels  = [str(r['day']) for r in daily]
    daily_counts  = [r['cnt'] for r in daily]
    daily_avgs    = [round(r['avg'], 2) if r['avg'] else 0 for r in daily]

    # Per-part breakdown
    part_breakdown = (
        TestSession.objects
        .filter(status='completed')
        .values('part')
        .annotate(cnt=Count('id'), avg=Avg('total_score'))
        .order_by('part')
    )

    # Top teachers by student count
    top_teachers = (
        StudentProfile.objects
        .values('teacher__name')
        .annotate(cnt=Count('id'))
        .filter(teacher__isnull=False)
        .order_by('-cnt')[:10]
    )

    # Recent registrations (last 14 days)
    reg_cutoff = tz.now() - tz.timedelta(days=14)
    recent_students = (
        StudentProfile.objects
        .filter(created_at__gte=reg_cutoff)
        .select_related('user', 'teacher')
        .order_by('-created_at')[:20]
    )

    return render(request, 'speaking_test/admin_analytics.html', {
        'total_students':  total_students,
        'total_sessions':  total_sessions,
        'total_outsiders': total_outsiders,
        'total_center':    total_center,
        'overall_avg':     round(overall_avg, 2) if overall_avg else None,
        'total_teachers':  total_teachers,
        'daily_labels':    daily_labels,
        'daily_counts':    daily_counts,
        'daily_avgs':      daily_avgs,
        'part_breakdown':  list(part_breakdown),
        'top_teachers':    list(top_teachers),
        'recent_students': recent_students,
    })


# ═══════════════════════════════════════════════════════════════════════════
#  ANNOUNCEMENTS — dismiss API
# ═══════════════════════════════════════════════════════════════════════════

@login_required
def dismiss_announcement(request, ann_id):
    if request.method == 'POST':
        from .models import Announcement, AnnouncementDismissal
        ann = get_object_or_404(Announcement, id=ann_id, show_once=True)
        AnnouncementDismissal.objects.get_or_create(announcement=ann, user=request.user)
    return JsonResponse({'ok': True})


# ═══════════════════════════════════════════════════════════════════════════
#  ACCESS CONTROL VIEWS
# ═══════════════════════════════════════════════════════════════════════════

def access_denied(request, reason='pending'):
    return render(request, 'speaking_test/access_denied.html', {'reason': reason})
