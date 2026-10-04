using System;
using System.Diagnostics;
using System.IO;
using System.Management;
using System.Threading;

/// <summary>
/// ArchiBox USB Watchdog
/// Detects when the ArchiBox USB key is inserted/ejected and launches/kills the agent.
/// Runs silently in background. Single exe, no install needed.
/// </summary>
class UsbWatch
{
    private static string? _agentProcessName = "archibox-agent";
    private static string? _keyDriveLetter;
    private static readonly string LogDir = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "ArchiBox", "logs");

    static void Main(string[] args)
    {
        try { Directory.CreateDirectory(LogDir); } catch { }

        Log("ArchiBox USB Watchdog started");
        Log($"Admin: {IsAdmin()}");

        // Watch for USB volume changes via WMI
        using var watcher = new ManagementEventWatcher(new WqlEventQuery(
            "SELECT * FROM Win32_VolumeChangeEvent WHERE EventType = 2 OR EventType = 3"));
        watcher.EventArrived += OnVolumeChange;
        watcher.Start();

        Log("Watching for USB changes... Press Ctrl+C to stop.");

        // Also check if agent is already running
        RestartAgentIfKeyPresent();

        // Keep alive
        try { Thread.Sleep(Timeout.Infinite); } catch { }
    }

    static void OnVolumeChange(object sender, EventArrivedEventArgs e)
    {
        try
        {
            var eName = e.NewEvent.Properties["EventType"]?.Value?.ToString();
            var driveName = e.NewEvent.Properties["DriveName"]?.Value?.ToString();
            var driveLetter = e.NewEvent.Properties["DriveLetter"]?.Value?.ToString();

            Log($"WMI Event: type={eName} drive={driveLetter}");

            if (eName == "2") // Device inserted
            {
                if (IsArchiBoxKey(driveLetter))
                {
                    Log($"ArchiBox key inserted at {driveLetter}");
                    LaunchAgent(driveLetter!);
                }
            }
            else if (eName == "3") // Device removed
            {
                if (_keyDriveLetter != null &&
                    driveLetter != null &&
                    driveLetter.TrimEnd(':') == _keyDriveLetter.TrimEnd(':'))
                {
                    Log($"ArchiBox key ejected from {driveLetter}");
                    StopAgent();
                    _keyDriveLetter = null;
                }
            }
        }
        catch (Exception ex)
        {
            Log($"WMI event error: {ex.Message}");
        }
    }

    static bool IsArchiBoxKey(string? driveLetter)
    {
        if (string.IsNullOrEmpty(driveLetter)) return false;

        try
        {
            var path = Path.Combine(driveLetter, "archibox.key");
            if (File.Exists(path))
            {
                _keyDriveLetter = driveLetter;
                return true;
            }
        }
        catch { }

        return false;
    }

    static void LaunchAgent(string driveLetter)
    {
        try
        {
            // Stop any existing agent first
            StopAgent();

            // Read token from key
            var tokenPath = Path.Combine(driveLetter, "token.txt");
            var configPath = Path.Combine(driveLetter, "config.json");

            string token = "", deviceId = "esp32s3-box-01", host = "192.168.0.119";
            int port = 8766;

            if (File.Exists(tokenPath))
                token = File.ReadAllText(tokenPath).Trim();

            if (File.Exists(configPath))
            {
                try
                {
                    using var json = System.Text.Json.JsonDocument.Parse(File.ReadAllText(configPath));
                    var root = json.RootElement;
                    if (root.TryGetProperty("device_id", out var d)) deviceId = d.GetString() ?? deviceId;
                    if (root.TryGetProperty("archimade_host", out var h)) host = h.GetString() ?? host;
                    if (root.TryGetProperty("archimade_port", out var p)) port = p.GetInt32();
                }
                catch { }
            }

            if (string.IsNullOrEmpty(token))
            {
                Log("ERROR: token.txt not found on USB key!");
                return;
            }

            // Find archibox-agent.exe next to this exe or in the same folder
            var exeDir = AppContext.BaseDirectory;
            var agentExe = Path.Combine(exeDir, "archibox-agent.exe");

            if (!File.Exists(agentExe))
            {
                // Try USB key root
                agentExe = Path.Combine(driveLetter, "archibox-agent.exe");
            }

            if (!File.Exists(agentExe))
            {
                Log($"ERROR: archibox-agent.exe not found in {exeDir} or {driveLetter}");
                return;
            }

            Log($"Launching agent: {agentExe} {token} {deviceId} {host} {port}");

            var psi = new ProcessStartInfo
            {
                FileName = agentExe,
                Arguments = $"\"{token}\" \"{deviceId}\" \"{host}\" {port}",
                UseShellExecute = false,
                CreateNoWindow = true
            };

            Process.Start(psi);
            Log("Agent launched.");
        }
        catch (Exception ex)
        {
            Log($"LaunchAgent error: {ex.Message}");
        }
    }

    static void StopAgent()
    {
        try
        {
            foreach (var proc in Process.GetProcessesByName(_agentProcessName))
            {
                Log($"Stopping agent (PID {proc.Id})");
                proc.Kill();
                try { proc.WaitForExit(3000); } catch { }
            }
        }
        catch (Exception ex)
        {
            Log($"StopAgent error: {ex.Message}");
        }
    }

    static void RestartAgentIfKeyPresent()
    {
        try
        {
            foreach (var drive in DriveInfo.GetDrives())
            {
                if (drive.IsReady && drive.DriveType == DriveType.Removable)
                {
                    if (IsArchiBoxKey(drive.Name))
                    {
                        Log($"Key already present at {drive.Name}, launching agent...");
                        LaunchAgent(drive.Name);
                        break;
                    }
                }
            }
        }
        catch { }
    }

    static bool IsAdmin()
    {
        try
        {
            using var identity = System.Security.Principal.WindowsIdentity.GetCurrent();
            var principal = new System.Security.Principal.WindowsPrincipal(identity);
            return principal.IsInRole(System.Security.Principal.WindowsBuiltInRole.Administrator);
        }
        catch { return false; }
    }

    static void Log(string msg)
    {
        var ts = DateTime.Now.ToString("HH:mm:ss");
        var line = $"[{ts}] {msg}";
        Console.WriteLine(line);
        try
        {
            File.AppendAllText(Path.Combine(LogDir, "usb-watch.log"), line + "\n");
        }
        catch { }
    }
}
