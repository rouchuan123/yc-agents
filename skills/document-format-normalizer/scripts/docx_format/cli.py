import argparse

from yc_agents.docx_format.pipeline import normalize_docx


def main(argv=None):
    parser = argparse.ArgumentParser(description="Normalize a DOCX draft.")
    parser.add_argument("source_path")
    parser.add_argument("output_dir")
    parser.add_argument("--template-name", default="report-standard")
    parser.add_argument("--template-path", default="")
    parser.add_argument("--output-name", default="normalized")
    args = parser.parse_args(argv)

    result = normalize_docx(
        source_path=args.source_path,
        output_dir=args.output_dir,
        template_name=args.template_name,
        template_path=args.template_path or None,
        output_name=args.output_name,
    )
    print(result.output_docx)
    print(result.audit_report)


if __name__ == "__main__":
    main()
