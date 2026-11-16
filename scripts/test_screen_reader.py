"""
AeroSync Screen Reader & AI Pipeline Test

Tests:
1. Screen capture (PIL Image & dimensions)
2. OCR text extraction
3. AI content analyzer fallback logic & ActionPlan generation
4. Text creator (writes to Desktop and verifies)
5. Action execution orchestrator
6. Package serialization / deserialization roundtrip with screen_content and action_plan
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.types.screen_types import ScreenRegion, ScreenContent, ActionPlan, ActionItem
from services.screen_reader.screen_capturer import capture_screen, image_to_base64_png
from services.screen_reader.ocr_engine import run_ocr
from services.ai_analyzer.content_analyzer import analyze_screen_content
from services.action_executor.text_creator import create_text_file
from services.action_executor.execution_orchestrator import execute_action_plan
from shared.types.workspace_types import WorkspaceSnapshot
from services.workspace_packager.packager import create_package, unpack_package


async def run_pipeline_test():
    print("=" * 60)
    print("AEROSYNC SCREEN READER & AI PIPELINE TEST")
    print("=" * 60)

    # 1. Screen Capture Test
    print("\n[1/6] Testing screen capture...")
    # Capture a small test region (e.g. 200x200 at 0,0) so we don't stress memory
    region = ScreenRegion(x=0, y=0, width=200, height=200)
    img = capture_screen(region)
    print(f"  ✓ Screen captured: format={img.format or 'RGB'}, size={img.size}, mode={img.mode}")
    assert img.size == (200, 200)

    b64 = image_to_base64_png(img)
    print(f"  ✓ Base64 PNG encoded: {len(b64)} chars")
    assert len(b64) > 100

    # 2. OCR Engine Test
    print("\n[2/6] Testing OCR engine...")
    ocr_res = run_ocr(img)
    print(f"  ✓ OCR executed via '{ocr_res.engine_used}': words={ocr_res.word_count}, confidence={ocr_res.confidence:.2f}")

    # 3. AI Content Analyzer Fallback Test
    print("\n[3/6] Testing AI content analyzer...")
    dummy_content = ScreenContent(
        region=region,
        ocr_text="Search Google for: Python async programming\nhttps://docs.python.org",
        screenshot_base64=b64,
        captured_at="2026-11-15T22:00:00Z",
        ocr_confidence=0.92,
        is_full_screen=False,
    )
    plan = analyze_screen_content(dummy_content)
    print(f"  ✓ ActionPlan generated: {len(plan.actions)} actions, fallback_used={plan.fallback_used}")
    print(f"    Summary: {plan.summary}")
    for a in plan.actions:
        print(f"    - Action: {a.type} -> {repr(a.content[:60])}")
    assert len(plan.actions) > 0

    # 4. Text Creator Test
    print("\n[4/6] Testing text creator...")
    test_text = "AeroSync Screen Reader Verification Test\nGenerated automatically."
    file_path = create_text_file(test_text, filename_hint="unit_test")
    print(f"  ✓ Text file created at: {file_path}")
    assert os.path.exists(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        read_back = f.read()
    assert read_back == test_text
    # Clean up test file
    try:
        os.remove(file_path)
        print("  ✓ Test file cleaned up")
    except Exception:
        pass

    # 5. Action Execution Orchestrator Test
    print("\n[5/6] Testing action executor orchestrator...")
    mock_plan = ActionPlan(
        actions=[
            ActionItem(type="create_text_file", content="Test line 1", filename_hint="exec_test"),
            ActionItem(type="open_url", content="about:blank", url="about:blank"),
        ],
        summary="Test action plan execution",
        overall_confidence=0.95,
    )
    # Execute action plan
    report = await execute_action_plan(mock_plan, transfer_id="test-transfer-123")
    print(f"  ✓ Executed {len(report.results)} actions: succeeded={report.succeeded}, failed={report.failed}")
    assert report.succeeded > 0
    # Clean up any created test file
    for r in report.results:
        if r.action_type == "create_text_file" and r.output and os.path.exists(r.output):
            try:
                os.remove(r.output)
            except Exception:
                pass

    # 6. Packager Round-Trip Test with Screen Data
    print("\n[6/6] Testing packaging roundtrip with ScreenContent & ActionPlan...")
    snapshot = WorkspaceSnapshot(
        snapshot_id="test-screen-snap-001",
        captured_at="2026-11-15T22:00:00Z",
        source_device_id="device-test",
        source_platform="windows",
        screen_content=dummy_content,
        action_plan=plan,
    )
    package = create_package(snapshot)
    print(f"  ✓ Package created: {package.total_size_bytes} bytes encrypted")

    unpacked = unpack_package(package.encrypted_payload, package.aes_key)
    print(f"  ✓ Package unpacked successfully: ID={unpacked.snapshot_id}")
    assert unpacked.snapshot_id == snapshot.snapshot_id
    assert unpacked.screen_content is not None
    assert unpacked.screen_content.ocr_text == dummy_content.ocr_text
    assert unpacked.action_plan is not None
    assert len(unpacked.action_plan.actions) == len(plan.actions)
    assert unpacked.action_plan.summary == plan.summary
    print("  ✓ ScreenContent and ActionPlan preserved perfectly across AES-256-GCM round-trip!")

    print("\n" + "=" * 60)
    print("ALL SCREEN READER & AI TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_pipeline_test())
