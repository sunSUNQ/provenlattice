import com.github.javaparser.ParserConfiguration;

import org.eclipse.jdt.core.JavaCore;
import org.eclipse.jdt.core.dom.AST;
import org.eclipse.jdt.core.dom.ASTParser;
import org.eclipse.jdt.core.dom.ASTVisitor;
import org.eclipse.jdt.core.dom.ClassInstanceCreation;
import org.eclipse.jdt.core.dom.CompilationUnit;
import org.eclipse.jdt.core.dom.FileASTRequestor;
import org.eclipse.jdt.core.dom.IBinding;
import org.eclipse.jdt.core.dom.IMethodBinding;
import org.eclipse.jdt.core.dom.ITypeBinding;
import org.eclipse.jdt.core.dom.MethodInvocation;
import org.eclipse.jdt.core.dom.SimpleType;
import org.eclipse.jdt.core.dom.TypeDeclaration;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

/** P2-B driver: JDT batch binding with stats, heap/CPU self-report and
 *  optional per-binding JSONL output. Modes: stats | full */
public class P2bDriver {
    static long filesParsed = 0, problemsTotal = 0;
    static long callsResolved = 0, callsRecovered = 0, callsAmbiguous = 0;
    static long typesResolved = 0, typesRecovered = 0, typesAmbiguous = 0;
    static long newsResolved = 0, newsRecovered = 0, newsAmbiguous = 0;
    static long parserInits = 0;

    static String esc(String s) {
        if (s == null) return "null";
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", " ").replace("\r", "") + "\"";
    }

    static boolean isRecoveredCall(IMethodBinding b) {
        return b.getDeclaringClass() != null && b.getDeclaringClass().isRecovered();
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 3) throw new IllegalArgumentException("usage: <root> <stats|full> <outFile>");
        Path root = Path.of(args[0]).toAbsolutePath();
        String mode = args[1];
        Path outFile = Path.of(args[2]);
        List<String> files = new ArrayList<>();
        try (Stream<Path> walk = Files.walk(root)) {
            walk.filter(p -> p.toString().endsWith(".java")).sorted()
                    .forEach(p -> files.add(p.toAbsolutePath().toString()));
        }
        ASTParser parser = ASTParser.newParser(AST.getJLSLatest());
        parserInits++;
        var options = JavaCore.getOptions();
        JavaCore.setComplianceOptions(JavaCore.VERSION_21, options);
        parser.setCompilerOptions(options);
        String[] cpEntries = args.length > 3 && !args[3].isBlank()
                ? args[3].split(";") : new String[0];
        parser.setEnvironment(cpEntries, new String[] {root.toString()}, null, true);
        parser.setResolveBindings(true);
        parser.setBindingsRecovery(true);
        parser.setKind(ASTParser.K_COMPILATION_UNIT);

        java.io.BufferedWriter detail = mode.equals("full")
                ? Files.newBufferedWriter(outFile, StandardCharsets.UTF_8) : null;
        long start = System.nanoTime();
        final List<String> sink = new ArrayList<>();
        parser.createASTs(files.toArray(new String[0]), null, new String[0],
                new FileASTRequestor() {
                    @Override
                    public void acceptAST(String sourcePath, CompilationUnit cu) {
                        filesParsed++;
                        problemsTotal += cu.getProblems().length;
                        String rel = root.relativize(Path.of(sourcePath)).toString().replace('\\', '/');
                        cu.accept(new ASTVisitor() {
                            @Override
                            public boolean visit(MethodInvocation node) {
                                IMethodBinding b = node.resolveMethodBinding();
                                if (b == null || b.getDeclaringClass() == null) {
                                    callsAmbiguous++;
                                } else if (isRecoveredCall(b)) {
                                    callsRecovered++;
                                } else {
                                    callsResolved++;
                                }
                                if (detail != null) {
                                    String decl = (b != null && b.getDeclaringClass() != null)
                                            ? b.getDeclaringClass().getQualifiedName() : null;
                                    String sig = (b != null) ? b.getName() + "()" : null;
                                    String rec = (b != null && b.getDeclaringClass() != null)
                                            ? String.valueOf(b.getDeclaringClass().isRecovered()) : "null";
                                    try {
                                        detail.write("{\"kind\":\"call\",\"file\":" + esc(rel)
                                                + ",\"line\":" + cu.getLineNumber(node.getStartPosition())
                                                + ",\"expr\":" + esc(node.getName().getIdentifier())
                                                + ",\"decl\":" + esc(decl)
                                                + ",\"signature\":" + esc(sig)
                                                + ",\"recovered\":" + rec + "}\n");
                                    } catch (IOException ignored) { }
                                }
                                return true;
                            }

                            @Override
                            public boolean visit(ClassInstanceCreation node) {
                                IMethodBinding b = node.resolveConstructorBinding();
                                ITypeBinding t = (b != null && b.getDeclaringClass() != null)
                                        ? b.getDeclaringClass() : node.getType().resolveBinding();
                                if (t == null) newsAmbiguous++;
                                else if (t.isRecovered()) newsRecovered++;
                                else newsResolved++;
                                if (detail != null) {
                                    try {
                                        detail.write("{\"kind\":\"new\",\"file\":" + esc(rel)
                                                + ",\"line\":" + cu.getLineNumber(node.getStartPosition())
                                                + ",\"expr\":" + esc(node.getType().toString())
                                                + ",\"decl\":" + esc(t == null ? null : t.getQualifiedName())
                                                + ",\"recovered\":" + (t == null ? "null" : t.isRecovered()) + "}\n");
                                    } catch (IOException ignored) { }
                                }
                                return true;
                            }

                            @Override
                            public boolean visit(SimpleType node) {
                                IBinding b = node.resolveBinding();
                                ITypeBinding t = (b != null && b.getKind() == IBinding.TYPE)
                                        ? (ITypeBinding) b : null;
                                if (t == null) typesAmbiguous++;
                                else if (t.isRecovered()) typesRecovered++;
                                else typesResolved++;
                                if (detail != null) {
                                    try {
                                        detail.write("{\"kind\":\"type\",\"file\":" + esc(rel)
                                                + ",\"line\":" + cu.getLineNumber(node.getStartPosition())
                                                + ",\"expr\":" + esc(node.toString())
                                                + ",\"decl\":" + esc(t == null ? null : t.getQualifiedName())
                                                + ",\"recovered\":" + (t == null ? "null" : t.isRecovered()) + "}\n");
                                    } catch (IOException ignored) { }
                                }
                                return true;
                            }
                        });
                    }
                }, null);
        long wallMs = (System.nanoTime() - start) / 1_000_000;
        if (detail != null) detail.close();
        Runtime rt = Runtime.getRuntime();
        com.sun.management.OperatingSystemMXBean os =
                (com.sun.management.OperatingSystemMXBean) ManagementFactory.getOperatingSystemMXBean();
        String summary = "{\"kind\":\"summary\",\"files_total\":" + files.size()
                + ",\"files_parsed\":" + filesParsed
                + ",\"problems_total\":" + problemsTotal
                + ",\"calls_resolved\":" + callsResolved + ",\"calls_recovered\":" + callsRecovered
                + ",\"calls_ambiguous\":" + callsAmbiguous
                + ",\"types_resolved\":" + typesResolved + ",\"types_recovered\":" + typesRecovered
                + ",\"types_ambiguous\":" + typesAmbiguous
                + ",\"news_resolved\":" + newsResolved + ",\"news_recovered\":" + newsRecovered
                + ",\"news_ambiguous\":" + newsAmbiguous
                + ",\"parser_inits\":" + parserInits
                + ",\"wall_ms\":" + wallMs
                + ",\"cpu_ms\":" + (os.getProcessCpuTime() / 1_000_000)
                + ",\"heap_used_mb\":" + ((rt.totalMemory() - rt.freeMemory()) / 1048576)
                + ",\"heap_max_mb\":" + (rt.maxMemory() / 1048576)
                + "}";
        Files.writeString(outFile, summary + System.lineSeparator(), StandardCharsets.UTF_8,
                java.nio.file.StandardOpenOption.CREATE,
                java.nio.file.StandardOpenOption.APPEND);
        System.out.println("P2B:" + summary);
    }
}
