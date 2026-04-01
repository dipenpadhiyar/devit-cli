"""{{project_name}} — AWS automation scripts entry point."""

import argparse
from scripts import s3, ec2


def main():
    parser = argparse.ArgumentParser(description="{{project_name}} AWS scripts")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list-buckets", help="List S3 buckets")
    sub.add_parser("list-instances", help="List EC2 instances")

    args = parser.parse_args()

    if args.command == "list-buckets":
        s3.list_buckets()
    elif args.command == "list-instances":
        ec2.list_instances()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
