$ErrorActionPreference = "Continue"

Write-Host "REEL INTELLIGENCE local capability report"
$Tools = @(
    @{ Label = "Python"; Name = "python" },
    @{ Label = "Tesseract OCR"; Name = "tesseract" },
    @{ Label = "Poppler PDF text"; Name = "pdftotext" },
    @{ Label = "FFmpeg"; Name = "ffmpeg" },
    @{ Label = "FFprobe"; Name = "ffprobe" },
    @{ Label = "whisper.cpp CLI"; Name = "whisper-cli" }
)

foreach ($Tool in $Tools) {
    $Resolved = Get-Command $Tool.Name -ErrorAction SilentlyContinue
    if ($Resolved) {
        Write-Host ("[FOUND]  {0,-18} {1}" -f $Tool.Label, $Resolved.Source)
    } else {
        Write-Host ("[MISSING] {0,-17} {1}" -f $Tool.Label, $Tool.Name)
    }
}

Write-Host ""
Write-Host "Model files are supplied by the operator; this script never downloads models."
Write-Host "The Python package itself has no mandatory processor dependency."
