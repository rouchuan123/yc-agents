import argparse

from yc_agents.docx_format.pipeline import normalize_docx


def main(argv=None):
    parser = argparse.ArgumentParser(description="规范化 DOCX 草稿格式。")
    parser.add_argument("source_path", help="源 Word .docx 文件路径")
    parser.add_argument("output_dir", help="输出目录")
    parser.add_argument(
        "--template-name",
        default="report-standard",
        help="内置模板名称，默认使用 report-standard",
    )
    parser.add_argument(
        "--template-path",
        default="",
        help="用户提供的 .docx 模板路径；为空时使用内置模板",
    )
    parser.add_argument(
        "--output-name",
        default="normalized",
        help="输出文件名主体，默认使用 normalized",
    )
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
