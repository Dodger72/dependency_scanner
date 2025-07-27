import os
import subprocess
import xml.etree.ElementTree as ET
import re

def clone_repository(repo_url, clone_dir):
    """Clones the Git repository to the specified directory."""
    if os.path.exists(clone_dir):
        print(f"Directory '{clone_dir}' already exists. Skipping clone.")
        return True # Assume it's already cloned
    print(f"Cloning '{repo_url}' into '{clone_dir}'...")
    try:
        subprocess.run(['git', 'clone', repo_url, clone_dir], check=True)
        print("Repository cloned successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error cloning repository: {e}")
        return False

def parse_maven_pom(pom_path):
    """Parses a Maven pom.xml file and extracts dependencies."""
    dependencies = []
    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()
        namespace = {'mvn': 'http://maven.apache.org/POM/4.0.0'}

        # Handle properties for version resolution
        properties = {}
        properties_node = root.find('mvn:properties', namespace)
        if properties_node is not None:
            for prop in properties_node:
                tag_name = prop.tag.replace(f"{{{namespace['mvn']}}}", '')
                properties[tag_name] = prop.text

        # Get parent version if available
        parent_version = None
        parent_node = root.find('mvn:parent', namespace)
        if parent_node is not None:
            parent_version_node = parent_node.find('mvn:version', namespace)
            if parent_version_node is not None:
                parent_version = parent_version_node.text

        # Find dependencies
        dependencies_node = root.find('mvn:dependencies', namespace)
        if dependencies_node is not None:
            for dep in dependencies_node.findall('mvn:dependency', namespace):
                group_id = dep.find('mvn:groupId', namespace)
                artifact_id = dep.find('mvn:artifactId', namespace)
                version = dep.find('mvn:version', namespace)

                if group_id is not None and artifact_id is not None:
                    resolved_version = None
                    if version is not None:
                        version_text = version.text
                        # Resolve properties in version
                        if version_text and version_text.startswith('${') and version_text.endswith('}'):
                            prop_name = version_text[2:-1]
                            resolved_version = properties.get(prop_name, 'UNKNOWN')
                        else:
                            resolved_version = version_text
                    elif parent_version:
                        # If version is not specified, it might be inherited from parent
                        resolved_version = parent_version

                    dependencies.append({
                        'groupId': group_id.text,
                        'artifactId': artifact_id.text,
                        'version': resolved_version if resolved_version else 'N/A' # Mark as N/A if version still couldn't be resolved
                    })
    except ET.ParseError as e:
        print(f"Error parsing XML for {pom_path}: {e}")
    except FileNotFoundError:
        print(f"File not found: {pom_path}")
    return dependencies

def parse_gradle_build_file(build_file_path):
    """Parses a Gradle build.gradle or build.gradle.kts file and extracts dependencies."""
    dependencies = []
    try:
        with open(build_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Regex to find common dependency declarations
        # This is a simplified regex and might need refinement for complex Gradle setups
        # It looks for:
        #   implementation 'group:artifact:version'
        #   implementation("group:artifact:version")
        #   implementation "group:artifact:version"
        #   compile 'group:artifact:version' (older syntax)
        #   implementation group: 'group', name: 'artifact', version: 'version'
        #   kotlin("group:artifact") version "1.0.0" (for build.gradle.kts)
        #   e.g. implementation(project(":some-module")) will be ignored for now.
        dependency_pattern = re.compile(
            r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testCompile|kapt|classpath|implementation\()[\s\"']*(?:([a-zA-Z0-9\._-]+):([a-zA-Z0-9\._-]+):([a-zA-Z0-9\._-]+(?:-\w+)*))[\"']*\)?|" # group:artifact:version
            r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation|testCompile|kapt|classpath)\s+group:\s*['\"]([a-zA-Z0-9\._-]+)['\"],\s*name:\s*['\"]([a-zA-Z0-9\._-]+)['\"],\s*version:\s*['\"]([a-zA-Z0-9\._-]+)['\"]" # group: 'g', name: 'a', version: 'v'
        )
        kotlin_dependency_pattern = re.compile(
            r"(?:kotlin|implementation|api|compileOnly|runtimeOnly|testImplementation)\([\"']([a-zA-Z0-9\._-]+):([a-zA-Z0-9\._-]+)[\"']\)\s+version\s+[\"']([a-zA-Z0-9\._-]+)[\"']" # kotlin("group:artifact") version "version"
        )


        matches = dependency_pattern.finditer(content)
        for match in matches:
            if match.group(1) and match.group(2) and match.group(3):
                dependencies.append({
                    'groupId': match.group(1),
                    'artifactId': match.group(2),
                    'version': match.group(3)
                })
            elif match.group(4) and match.group(5) and match.group(6):
                dependencies.append({
                    'groupId': match.group(4),
                    'artifactId': match.group(5),
                    'version': match.group(6)
                })
        
        kotlin_matches = kotlin_dependency_pattern.finditer(content)
        for match in kotlin_matches:
            dependencies.append({
                'groupId': match.group(1),
                'artifactId': match.group(2),
                'version': match.group(3)
            })

    except FileNotFoundError:
        print(f"File not found: {build_file_path}")
    return dependencies

def generate_dependency_report(repo_path):
    """Generates a report of all dependencies found in the repository."""
    project_dependencies = {}
    for root, _, files in os.walk(repo_path):
        is_project_root = False
        for file in files:
            if file == 'pom.xml':
                pom_path = os.path.join(root, file)
                print(f"Found Maven project: {pom_path}")
                deps = parse_maven_pom(pom_path)
                if deps:
                    project_dependencies[root] = deps
                is_project_root = True
                break # Only process one build file per project root
            elif file.endswith('build.gradle') or file.endswith('build.gradle.kts'):
                gradle_path = os.path.join(root, file)
                print(f"Found Gradle project: {gradle_path}")
                deps = parse_gradle_build_file(gradle_path)
                if deps:
                    project_dependencies[root] = deps
                is_project_root = True
                break # Only process one build file per project root
        
        # Optimization: if a project root is found, skip descending into its subdirectories for
        # finding other build files if those subdirectories are likely to be part of the current
        # project. This is a heuristic and might need adjustment.
        # This simple check ensures we don't treat nested modules as separate projects
        # unless they explicitly define their own build files.
        if is_project_root:
            # os.walk will continue, but we've already identified the "project" here.
            # For deeper nested projects, the outer loop will pick them up as new "roots".
            pass

    return project_dependencies

def main():
    repo_url = input("Enter the Git repository URL: ")
    clone_dir = "cloned_repo002" # Or ask for user input
    
    if not clone_repository(repo_url, clone_dir):
        print("Failed to clone repository. Exiting.")
        return

    print("\nScanning for dependencies...")
    report = generate_dependency_report(clone_dir)

    if not report:
        print("No Maven or Gradle projects with dependencies found.")
        return

    print("\n--- Dependency Report ---")
    for project_path, dependencies in report.items():
        print(f"\nProject: {project_path.replace(clone_dir + os.sep, '')}") # Make path relative
        if not dependencies:
            print("  No dependencies found.")
            continue
        for dep in dependencies:
            print(f"  - Group: {dep.get('groupId', 'N/A')}, Artifact: {dep.get('artifactId', 'N/A')}, Version: {dep.get('version', 'N/A')}")
    
    # Optional: Save report to a file
    with open("dependency_report.txt", "w", encoding="utf-8") as f:
        f.write("--- Dependency Report ---\n")
        for project_path, dependencies in report.items():
            f.write(f"\nProject: {project_path.replace(clone_dir + os.sep, '')}\n")
            if not dependencies:
                f.write("  No dependencies found.\n")
                continue
            for dep in dependencies:
                f.write(f"  - Group: {dep.get('groupId', 'N/A')}, Artifact: {dep.get('artifactId', 'N/A')}, Version: {dep.get('version', 'N/A')}\n")
    print("\nReport saved to dependency_report.txt")

if __name__ == "__main__":
    main()