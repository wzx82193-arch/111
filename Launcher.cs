using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

internal static class Launcher
{
    [STAThread]
    private static int Main(string[] args)
    {
        bool smoke = args.Length == 2 && args[0] == "--smoke";
        string temporary = Path.Combine(Path.GetTempPath(), "ProfileStudio-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(temporary);
            using (Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("Runtime.zip"))
            using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read))
            {
                archive.ExtractToDirectory(temporary);
            }
            string command = "-E -s -B \"" + Path.Combine(temporary, "app.py") + "\"";
            if (smoke)
            {
                command += " --smoke \"" + Path.GetFullPath(args[1]).TrimEnd('\\') + "\"";
            }
            var info = new ProcessStartInfo(
                Path.Combine(temporary, smoke ? "python.exe" : "pythonw.exe"), command);
            info.WorkingDirectory = Environment.CurrentDirectory;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.EnvironmentVariables["MPLCONFIGDIR"] = Path.Combine(temporary, "mpl-cache");
            info.EnvironmentVariables["TCL_LIBRARY"] = Path.Combine(temporary, "tcl", "tcl8.6");
            info.EnvironmentVariables["TK_LIBRARY"] = Path.Combine(temporary, "tcl", "tk8.6");
            using (Process child = Process.Start(info))
            {
                child.WaitForExit();
                if (child.ExitCode != 0 && !smoke)
                {
                    MessageBox.Show("程序启动或运行失败。错误代码 " + child.ExitCode, "测量曲线分析");
                }
                return child.ExitCode;
            }
        }
        catch (Exception error)
        {
            if (!smoke) MessageBox.Show(error.Message, "测量曲线分析");
            return 1;
        }
        finally
        {
            try { Directory.Delete(temporary, true); }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }
}
