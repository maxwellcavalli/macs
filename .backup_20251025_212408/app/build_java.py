from __future__ import annotations
from pathlib import Path
from typing import Tuple
import textwrap
from .exec_sandbox import run_sandboxed

LOG_TAIL_BYTES = 2000

def _tail(s: str, nbytes: int = LOG_TAIL_BYTES) -> str:
    enc = (s or "").encode("utf-8", errors="ignore")
    return enc[-nbytes:].decode("utf-8", errors="ignore")

async def _run_gradle(workdir: Path) -> Tuple[bool, bool, str, str]:
    # Prefer wrapper if present
    gradlew = workdir / "gradlew"
    if not gradlew.exists():
        return False, False, "", "gradle wrapper not found"
    gradlew.chmod(0o755)
    # compile + test
    res = await run_sandboxed(["./gradlew", "-q", "--no-daemon", "clean", "test"], cwd=str(workdir), timeout=300)
    out, err = _tail(res.stdout), _tail(res.stderr)
    compile_pass = res.returncode == 0  # Gradle returns non-zero if compile or test fails
    test_pass = res.returncode == 0
    return compile_pass, test_pass, out, err

def _write_minimal_maven_project(root: Path, src_rel: str):
    """
    Create a tiny Maven project if none exists, place class & a trivial test.
    JUnit 5 via maven-central.
    """
    pom = textwrap.dedent("""\
    <project xmlns="http://maven.apache.org/POM/4.0.0"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
      <modelVersion>4.0.0</modelVersion>
      <groupId>com.acme</groupId>
      <artifactId>demo</artifactId>
      <version>0.0.1</version>
      <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.10.2</junit.version>
      </properties>
      <dependencies>
        <dependency>
          <groupId>org.junit.jupiter</groupId>
          <artifactId>junit-jupiter</artifactId>
          <version>${junit.version}</version>
          <scope>test</scope>
        </dependency>
      </dependencies>
      <build>
        <plugins>
          <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.2.5</version>
            <configuration>
              <useModulePath>false</useModulePath>
            </configuration>
          </plugin>
        </plugins>
      </build>
    </project>
    """)
    (root / "pom.xml").write_text(pom, encoding="utf-8")
    # Ensure src tree exists for tests
    (root / "src" / "test" / "java" / "com" / "acme").mkdir(parents=True, exist_ok=True)
    # Basic test that compiles & runs without touching app code
    t = textwrap.dedent("""\
    package com.acme;
    import org.junit.jupiter.api.Test;
    import static org.junit.jupiter.api.Assertions.assertTrue;
    public class SmokeTest {
        @Test public void ok() { assertTrue(true); }
    }
    """)
    (root / "src" / "test" / "java" / "com" / "acme" / "SmokeTest.java").write_text(t, encoding="utf-8")

async def _run_maven(workdir: Path) -> Tuple[bool, bool, str, str]:
    # compile + test; first ensure pom.xml exists
    pom = workdir / "pom.xml"
    if not pom.exists():
        # create minimal pom and trivial test
        _write_minimal_maven_project(workdir, "")
    res = await run_sandboxed(["mvn", "-q", "-DskipITs", "test"], cwd=str(workdir), timeout=420)
    out, err = _tail(res.stdout), _tail(res.stderr)
    # Maven returns non-zero on either compile or test failure
    compile_pass = res.returncode == 0
    test_pass = res.returncode == 0
    return compile_pass, test_pass, out, err

async def build_and_test_java(workdir: Path) -> Tuple[bool, bool, str, str, str]:
    """
    Decide tool:
      - gradle wrapper -> use it
      - else if pom.xml -> mvn
      - else -> create minimal maven project and mvn test
    Returns: (compile_pass, test_pass, out_tail, err_tail, tool_used)
    """
    if (workdir / "gradlew").exists():
        c, t, o, e = await _run_gradle(workdir)
        return c, t, o, e, "gradle"
    if (workdir / "pom.xml").exists():
        c, t, o, e = await _run_maven(workdir)
        return c, t, o, e, "maven"
    # default: scaffold minimal maven project
    c, t, o, e = await _run_maven(workdir)
    return c, t, o, e, "maven-scaffolded"
