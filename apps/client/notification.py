"""
AeroSync Client Notifications

Native Windows Toast Notifications using PowerShell.
No extra Python dependencies required.
"""

import logging
import os
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)

def show_toast(title: str, message: str) -> None:
    """
    Show a native Windows 10/11 toast notification.
    
    Args:
        title: Notification title.
        message: Notification body.
    """
    logger.info(f"Notification: {title} - {message}")
    
    # Escape single quotes for PowerShell
    safe_title = title.replace("'", "''")
    safe_message = message.replace("'", "''")
    
    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $template = @"
    <toast>
        <visual>
            <binding template="ToastText02">
                <text id="1">{safe_title}</text>
                <text id="2">{safe_message}</text>
            </binding>
        </visual>
    </toast>
"@

    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($template)
    
    $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("AeroSync").Show($toast)
    """
    
    try:
        # Run in background so it doesn't block
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception as e:
        logger.error(f"Failed to show toast notification: {e}")


def show_toast_list(title: str, items: List[str], report_path: str = "") -> None:
    """
    Show a toast notification for a list of items (e.g. failed transfers).
    
    If <= 3 items: shows them inline.
    If > 3 items: shows count + saves a detailed text file.
    
    Args:
        title: Notification title.
        items: List of item descriptions.
        report_path: Optional path to save the full report (auto-generated if empty).
    """
    if not items:
        return

    if len(items) <= 3:
        body = "\n".join(f"• {i}" for i in items)
        show_toast(title, body)
    else:
        # Save to file
        if not report_path:
            import time
            ts = time.strftime("%Y%m%d_%H%M%S")
            report_path = os.path.join(
                os.path.expanduser("~"), f"AeroSync_failed_transfer_{ts}.txt"
            )
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(f"{title}\n")
                f.write("=" * len(title) + "\n\n")
                for item in items:
                    f.write(f"• {item}\n")
            body = f"{len(items)} items could not be transferred.\nSee: {report_path}"
        except Exception:
            body = f"{len(items)} items could not be transferred."

        show_toast(title, body)
        logger.info("[Notification] Saved failed transfer report: %s", report_path)


def show_failed_transfer_report(
    transfer_id: str,
    failed_items: List[str],
    reused_items: Optional[List[str]] = None,
    launched_apps: Optional[List[str]] = None,
    restored_tabs: Optional[List[str]] = None,
) -> None:
    """
    Show a comprehensive post-transfer notification.
    
    - If everything succeeded: shows a success toast.
    - If some items failed: shows a warning toast with the list.
    
    Args:
        transfer_id: The transfer ID (for file naming).
        failed_items: List of items that could not be transferred.
        reused_items: Items already on B that were reused.
        launched_apps: Apps successfully launched.
        restored_tabs: Browser tabs successfully opened.
    """
    reused_items = reused_items or []
    launched_apps = launched_apps or []
    restored_tabs = restored_tabs or []

    if not failed_items:
        parts = []
        if launched_apps:
            parts.append(f"{len(launched_apps)} app(s) launched")
        if restored_tabs:
            parts.append(f"{len(restored_tabs)} tab(s) restored")
        if reused_items:
            parts.append(f"{len(reused_items)} item(s) already present (reused)")
        body = ", ".join(parts) if parts else "Workspace fully reconstructed."
        show_toast("✅ AeroSync — Transfer Complete", body)
    else:
        import time
        ts = time.strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(
            os.path.expanduser("~"), f"AeroSync_failed_{transfer_id[:8]}_{ts}.txt"
        )
        show_toast_list(
            f"⚠️ AeroSync — {len(failed_items)} Item(s) Not Transferred",
            failed_items,
            report_path=report_path,
        )
