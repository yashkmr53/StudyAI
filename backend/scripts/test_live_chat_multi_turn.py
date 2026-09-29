"""Live verification script for Phase 10D: Multi-Turn Chat Context with qwen3.5:4b."""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
import django
django.setup()

from django.contrib.auth import get_user_model
from django.conf import settings
from apps.profiles.models import Profile
from apps.subjects.models import Subject
from apps.chat.models import ChatSession, ChatMessage
from apps.chat.services import ChatService

User = get_user_model()

def run_live_multi_turn_verification():
    print("=" * 70)
    print("Phase 10D: Live End-to-End Multi-Turn Chatbot Verification")
    print(f"Target LLM: {settings.LLM_MODEL}")
    print("=" * 70)

    user, _ = User.objects.get_or_create(email="phase10d@studyai.test", defaults={"first_name": "Phase10D"})
    profile, _ = Profile.objects.get_or_create(user=user, module=Profile.Module.AI_CLASSROOM, defaults={"name": "Phase 10D Profile"})
    subject, _ = Subject.objects.get_or_create(profile=profile, name="Machine Learning")

    session = ChatSession.objects.create(
        profile=profile,
        subject=subject,
        title="Live Multi-Turn Context Session",
    )
    print(f"[1] Created test ChatSession: {session.id} for user '{user.email}'")

    # Turn 1: Explain backpropagation
    print("\n[2] Turn 1: 'Explain backpropagation.'")
    msg1 = ChatService.ask(session, "Explain backpropagation.")
    print(f"    Assistant Turn 1: {msg1.content[:200]}...")
    assert msg1.model == "qwen3.5:4b", f"Expected qwen3.5:4b, got {msg1.model}"
    assert "backpropagation" in msg1.content.lower() or "gradient" in msg1.content.lower() or "neural" in msg1.content.lower()

    # Turn 2: Follow-up continuation 'yes'
    print("\n[3] Turn 2: 'yes'")
    msg2 = ChatService.ask(session, "yes")
    print(f"    Assistant Turn 2: {msg2.content[:250]}...")
    assert msg2.model == "qwen3.5:4b", f"Expected qwen3.5:4b, got {msg2.model}"

    # Verify that Turn 2 does NOT treat "yes" as a brand new conversation
    lower_content = msg2.content.lower()
    assert not ("it seems like you're ready to dive into some study material" in lower_content), "Turn 2 treated 'yes' as a new conversation!"
    assert any(term in lower_content for term in ["backpropagation", "gradient", "activation", "math", "weight", "layer", "error", "derivative", "loss", "learn", "neural"]), \
        f"Turn 2 did not continue the backpropagation context! Output: {msg2.content}"

    # Turn 3: Contextual follow-up
    print("\n[4] Turn 3: 'Can you give an example?'")
    msg3 = ChatService.ask(session, "Can you give an example?")
    print(f"    Assistant Turn 3: {msg3.content[:250]}...")
    assert msg3.model == "qwen3.5:4b", f"Expected qwen3.5:4b, got {msg3.model}"

    # Audit database messages
    all_msgs = list(session.messages.order_by("created_at"))
    print(f"\n[5] Database Audit: Total Messages = {len(all_msgs)}")
    for i, m in enumerate(all_msgs, 1):
        print(f"    Msg {i} [{m.role}]: {m.content[:60]}... (model={m.model or 'user'})")

    assert len(all_msgs) == 6, f"Expected 6 messages (3 user + 3 assistant), got {len(all_msgs)}"
    assert all_msgs[0].role == "user" and all_msgs[0].content == "Explain backpropagation."
    assert all_msgs[1].role == "assistant"
    assert all_msgs[2].role == "user" and all_msgs[2].content == "yes"
    assert all_msgs[3].role == "assistant"
    assert all_msgs[4].role == "user" and all_msgs[4].content == "Can you give an example?"
    assert all_msgs[5].role == "assistant"

    print("\n" + "=" * 70)
    print("LIVE MULTI-TURN VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_live_multi_turn_verification()
