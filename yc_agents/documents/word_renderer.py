import argparse
import json
import shutil
import tempfile
from pathlib import Path


def export_word_pdf(input_path, output_path):
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("Word rendering requires the Windows-only pywin32 dependency") from exc

    pythoncom.CoInitialize()
    word = None
    document = None
    temporary_directory = None
    # 安全设置失败不再静默吞掉：逐项记录降级项，随结果返回，由
    # verifier 转成 environment 类 warning 告知用户。
    security_degraded = []
    try:
        # Never let Word rewrite an immutable revision. Field and TOC refreshes
        # happen on a disposable copy inside the broker-approved QA directory.
        temporary_directory = Path(
            tempfile.mkdtemp(prefix="word-export-", dir=str(output_path.parent))
        )
        working_copy = temporary_directory / input_path.name
        shutil.copy2(input_path, working_copy)
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        try:
            # msoAutomationSecurityForceDisable：禁用文档宏。
            word.AutomationSecurity = 3
        except Exception:
            security_degraded.append("automation_security")
        try:
            word.Options.UpdateLinksAtOpen = False
        except Exception:
            security_degraded.append("update_links_at_open")
        document = word.Documents.Open(
            str(working_copy),
            ConfirmConversions=False,
            ReadOnly=False,
            AddToRecentFiles=False,
            NoEncodingDialog=True,
        )
        try:
            document.Fields.Update()
            for toc in document.TablesOfContents:
                toc.Update()
        except Exception:
            pass
        document.ExportAsFixedFormat(
            OutputFileName=str(output_path),
            ExportFormat=17,
            OpenAfterExport=False,
            OptimizeFor=0,
            Range=0,
            Item=0,
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=1,
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )
    finally:
        if document is not None:
            document.Close(SaveChanges=False)
        if word is not None:
            word.Quit()
        pythoncom.CoUninitialize()
        if temporary_directory is not None:
            shutil.rmtree(temporary_directory, ignore_errors=True)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Microsoft Word did not produce a non-empty PDF")
    return {
        "ok": True,
        "input": str(input_path),
        "output": str(output_path),
        "bytes": output_path.stat().st_size,
        "security_degraded": security_degraded,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = export_word_pdf(args.input, args.output)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
