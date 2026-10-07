using System.Diagnostics;
using System.Windows.Forms;

static string? FindRepo()
{
    var env = Environment.GetEnvironmentVariable("OPENJARVIS_HOME");
    if (!string.IsNullOrWhiteSpace(env) && Directory.Exists(env))
        return env;

    var preferred = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
        "source", "repos", "OpenJarvis");
    if (Directory.Exists(preferred))
        return preferred;

    var current = new DirectoryInfo(AppContext.BaseDirectory);
    while (current is not null)
    {
        if (Directory.Exists(Path.Combine(current.FullName, "frontend")) &&
            Directory.Exists(Path.Combine(current.FullName, "src")))
            return current.FullName;
        current = current.Parent;
    }
    return null;
}

static async Task<bool> IsUp(string url)
{
    try
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        using var response = await client.GetAsync(url);
        return response.IsSuccessStatusCode;
    }
    catch
    {
        return false;
    }
}

static void StartHidden(string file, string args, string workingDirectory)
{
    Process.Start(new ProcessStartInfo
    {
        FileName = file,
        Arguments = args,
        WorkingDirectory = workingDirectory,
        UseShellExecute = false,
        CreateNoWindow = true,
        WindowStyle = ProcessWindowStyle.Hidden,
    });
}

static async Task WaitFor(string url, int seconds)
{
    var until = DateTime.UtcNow.AddSeconds(seconds);
    while (DateTime.UtcNow < until)
    {
        if (await IsUp(url))
            return;
        await Task.Delay(500);
    }
}

var repo = FindRepo();
if (repo is null)
{
    MessageBox.Show(
        "No se encontró la carpeta de OpenJarvis. Define OPENJARVIS_HOME.",
        "JARVIS",
        MessageBoxButtons.OK,
        MessageBoxIcon.Error);
    return;
}

var pythonw = Path.Combine(repo, ".venv", "Scripts", "pythonw.exe");
if (!await IsUp("http://127.0.0.1:8000/health") && File.Exists(pythonw))
{
    StartHidden(
        pythonw,
        "-m openjarvis.cli serve --host 127.0.0.1 --port 8000",
        repo);
    await WaitFor("http://127.0.0.1:8000/health", 20);
}

var frontend = Path.Combine(repo, "frontend");
if (!await IsUp("http://127.0.0.1:5173/dashboard"))
{
    var npm = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
        "nodejs", "npm.cmd");
    if (!File.Exists(npm))
        npm = @"C:\Program Files\nodejs\npm.cmd";

    StartHidden(
        "cmd.exe",
        $"/c \"\"{npm}\" run dev -- --host 127.0.0.1 --port 5173 --strictPort\"",
        frontend);
    await WaitFor("http://127.0.0.1:5173/dashboard", 20);
}

var voiceScript = Path.Combine(repo, "scripts", "start-jarvis-voice.ps1");
if (File.Exists(voiceScript))
{
    StartHidden(
        "powershell.exe",
        $"-NoProfile -ExecutionPolicy Bypass -File \"{voiceScript}\"",
        repo);
}

var edgeCandidates = new[]
{
    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
        "Microsoft", "Edge", "Application", "msedge.exe"),
    Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
        "Microsoft", "Edge", "Application", "msedge.exe"),
};
var edge = edgeCandidates.FirstOrDefault(File.Exists);

if (edge is not null)
{
    Process.Start(new ProcessStartInfo
    {
        FileName = edge,
        Arguments = "--app=http://127.0.0.1:5173/dashboard --start-maximized",
        UseShellExecute = true,
    });
}
else
{
    Process.Start(new ProcessStartInfo
    {
        FileName = "http://127.0.0.1:5173/dashboard",
        UseShellExecute = true,
    });
}
