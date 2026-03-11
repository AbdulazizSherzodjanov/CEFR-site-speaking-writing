"""
Management command: cleanup_audio
Deletes audio recording files older than AUDIO_RETAIN_DAYS (default 2 days).

Usage:
    python manage.py cleanup_audio           # dry run — shows what would be deleted
    python manage.py cleanup_audio --delete  # actually deletes files

Schedule with cron (runs every day at 3 AM):
    0 3 * * * /path/to/venv/bin/python /path/to/manage.py cleanup_audio --delete >> /var/log/speakpro_cleanup.log 2>&1
"""
import os
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from speaking_test.models import TestSession, QuestionResponse

# How many days to keep audio files after a session completes
AUDIO_RETAIN_DAYS = getattr(settings, 'AUDIO_RETAIN_DAYS', 2)


class Command(BaseCommand):
    help = f'Delete audio recordings older than {AUDIO_RETAIN_DAYS} days to save disk space'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Actually delete files. Without this flag, runs in dry-run mode.',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=AUDIO_RETAIN_DAYS,
            help=f'Days to retain audio (default: {AUDIO_RETAIN_DAYS})',
        )

    def handle(self, *args, **options):
        dry_run = not options['delete']
        retain_days = options['days']
        cutoff = timezone.now() - timezone.timedelta(days=retain_days)

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN — pass --delete to actually remove files\n'
                f'Cutoff: {cutoff.strftime("%Y-%m-%d %H:%M")} ({retain_days} days ago)\n'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'DELETING audio files older than {retain_days} days\n'
                f'Cutoff: {cutoff.strftime("%Y-%m-%d %H:%M")}\n'
            ))

        # Find completed sessions whose audio is due for deletion
        sessions = TestSession.objects.filter(
            status='completed',
            audio_deleted=False,
            telegram_sent=True,      # only delete after Telegram has received it
            completed_at__lte=cutoff
        ).prefetch_related('responses')

        total_files = 0
        total_bytes = 0
        sessions_cleaned = 0

        for session in sessions:
            session_files = 0
            session_bytes = 0

            for response in session.responses.all():
                if response.audio_file:
                    try:
                        path = response.audio_file.path
                        if os.path.exists(path):
                            size = os.path.getsize(path)
                            session_bytes += size
                            total_bytes += size
                            session_files += 1
                            total_files += 1

                            if not dry_run:
                                os.remove(path)
                                response.audio_file = None
                                response.save(update_fields=['audio_file'])
                        else:
                            # File already gone, just clear the field
                            if not dry_run:
                                response.audio_file = None
                                response.save(update_fields=['audio_file'])
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(
                            f'  Error processing Q{response.question_number} '
                            f'of session {session.id}: {e}'
                        ))

            if session_files > 0 or True:
                action = 'Would delete' if dry_run else 'Deleted'
                self.stdout.write(
                    f'  {action}: {session.full_name} | Part {session.part} | '
                    f'{session.completed_at.strftime("%Y-%m-%d")} | '
                    f'{session_files} file(s) | {_fmt_bytes(session_bytes)}'
                )

            if not dry_run:
                session.audio_deleted = True
                session.save(update_fields=['audio_deleted'])
                sessions_cleaned += 1

        # Summary
        self.stdout.write('\n' + '─' * 60)
        action = 'Would free' if dry_run else 'Freed'
        self.stdout.write(self.style.SUCCESS(
            f'{"Sessions:" if not dry_run else "Sessions to clean:"} '
            f'{sessions.count() if dry_run else sessions_cleaned}\n'
            f'Files: {total_files}\n'
            f'{action}: {_fmt_bytes(total_bytes)}'
        ))

        # Also handle sessions where telegram was never sent but are very old (> 7 days)
        # This prevents files piling up if Telegram failed
        old_unsent = TestSession.objects.filter(
            status='completed',
            audio_deleted=False,
            completed_at__lte=timezone.now() - timezone.timedelta(days=7)
        )
        if old_unsent.exists():
            self.stdout.write(self.style.WARNING(
                f'\n⚠ {old_unsent.count()} session(s) completed >7 days ago '
                f'but Telegram not sent — also cleaning these up'
            ))
            for session in old_unsent:
                for response in session.responses.all():
                    if response.audio_file:
                        try:
                            if not dry_run:
                                path = response.audio_file.path
                                if os.path.exists(path):
                                    os.remove(path)
                                response.audio_file = None
                                response.save(update_fields=['audio_file'])
                        except Exception:
                            pass
                if not dry_run:
                    session.audio_deleted = True
                    session.save(update_fields=['audio_deleted'])


def _fmt_bytes(b):
    if b < 1024:
        return f'{b} B'
    elif b < 1024 ** 2:
        return f'{b / 1024:.1f} KB'
    elif b < 1024 ** 3:
        return f'{b / 1024 ** 2:.1f} MB'
    return f'{b / 1024 ** 3:.2f} GB'
