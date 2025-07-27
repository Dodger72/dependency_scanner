import os
import csv
import shutil
import subprocess
import xml.etree.ElementTree as ET

# List of your Git repository URLs
repositories = [
    "https://github.com/your-org/repo1.git",
    "https://github.com/your-org/repo2.git",
    "https://github.com/your-org/repo3.git",
]

# Output CSV file
output_file = "dependency_report.csv"

# Columns for the CSV report
csv_columns = ["Repository", "File", "Group ID", "Artifact ID", "Version"]

def clone_repo(repo_url, clone_dir):
    """Clones a Git repository into a specified directory."""
    print(f"Cloning {repo_url} into {clone_dir}...")
    try:
        subprocess.run(["git", "clone", repo_url, clone_dir], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error cloning repository {repo_url}: {e}")
        return False
    return True

def parse_pom(file_path):
    """Parses a Maven pom.xml file to extract dependencies."""
    dependencies = []
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        namespace = {'mvn': 'http://maven.apache.org/POM/4.0.0'}

        # Find the dependencies section
        for dependency in root.findall(".//mvn:dependencies/mvn:dependency", namespace):
            group_id = dependency.find("mvn:groupId", namespace)
            artifact_id = dependency.find("mvn:artifactId", namespace)
            version = dependency.find("mvn:version", namespace)

            if group_id is not None and artifact_id is not None:
                dependencies.append({
                    "groupId": group_id.text,
                    "artifactId": artifact_id.text,
                    "version": version.text if version is not None else "N/A"
                })
    except ET.ParseError as e:
        print(f"Error parsing XML file {file_path}: {e}")
    return dependencies

def parse_gradle_file(file_path):
    """Parses a Gradle build.gradle file to extract dependencies."""
    dependencies = []
    with open(file_path, 'r') as f:
        for line in f:
            # Simple regex to find a dependency declaration
            # This is a basic example and might need to be more complex
            # to handle all Gradle syntax variations.
            if "implementation" in line or "compile" in line:
                # Example: implementation 'group:artifact:version'
                match = re.search(r"['\"]([^:]+):([^:]+):([^'\"]+)['\"]", line)
                if match:
                    group, artifact, version = match.groups()
                    dependencies.append({
                        "groupId": group,
                        "artifactId": artifact,
                        "version": version
                    })
    return dependencies


def main():
    """Main function to orchestrate the process."""
    all_dependencies = []

    for repo_url in repositories:
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        clone_dir = os.path.join("/tmp", repo_name)  # Use a temporary directory

        if clone_repo(repo_url, clone_dir):
            for root, dirs, files in os.walk(clone_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    if file == "pom.xml":
                        deps = parse_pom(file_path)
                        for dep in deps:
                            all_dependencies.append({
                                "Repository": repo_name,
                                "File": os.path.relpath(file_path, clone_dir),
                                "Group ID": dep["groupId"],
                                "Artifact ID": dep["artifactId"],
                                "Version": dep["version"]
                            })
                    elif file == "build.gradle":
                        deps = parse_gradle_file(file_path)
                        for dep in deps:
                            all_dependencies.append({
                                "Repository": repo_name,
                                "File": os.path.relpath(file_path, clone_dir),
                                "Group ID": dep["groupId"],
                                "Artifact ID": dep["artifactId"],
                                "Version": dep["version"]
                            })
            
            # Cleanup the cloned directory
            shutil.rmtree(clone_dir)
    
    # Write the report to a CSV file
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
        writer.writeheader()
        writer.writerows(all_dependencies)
    
    print(f"Report generated successfully at {output_file}")

if __name__ == "__main__":
    import re # import re for the parse_gradle_file function
    main()