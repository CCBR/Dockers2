#!/usr/bin/env python
import json
import subprocess
import argparse
import shutil

# Set up argument parsing
parser = argparse.ArgumentParser(
    description="Generate a Markdown table of command versions from a JSON file."
)
parser.add_argument(
    "--json",
    required=True,
    type=str,
    help="Path to the JSON file containing commands and their version commands.",
)
parser.add_argument(
    "--output",
    required=False,
    type=str,
    help="Output file path. If not specified, output will be printed to stdout.",
)


def create_table(args):
    # Load JSON data
    with open(args.json, "r") as file:
        commands = json.load(file)

    # Prepare table header
    output_list = ["", "| Tool | Version |", "|---------|---------|"]

    # Run each command and capture output
    for command_name, version_command in commands.items():
        if shutil.which(command_name):
            try:
                # Run the command and capture its output
                result = subprocess.run(
                    version_command,
                    shell=True,
                    check=True,
                    text=True,
                    capture_output=True,
                )
                version_info = (
                    result.stdout.strip() if result.stdout else result.stderr.strip()
                )
                version_info = (
                    version_info.strip()
                    .replace('"', "")
                    .replace("'", "")
                    .replace("(", "")
                    .replace(")", "")
                )
                version_info = version_info.strip() or "VERSIONUNKNOWN"
            except subprocess.CalledProcessError:
                # If the command doesn't exist, handle the exception
                version_info = "NOTINDOCKER"
        else:
            version_info = "NOTINDOCKER"
        # Print in Markdown table format
        output_list.append(f"| {command_name} | {version_info} |")
    output_list.append("")
    return output_list


def main(args):
    output_list = create_table(args)
    output_str = "\n".join(output_list)

    if args.output:
        with open(args.output, "w") as outfile:
            outfile.write(output_str)
    else:
        print(output_str, end="")


if __name__ == "__main__":
    args = parser.parse_args()
    main(args)
