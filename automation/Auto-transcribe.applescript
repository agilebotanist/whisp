-- Folder Action: transcribes any audio file added to the attached folder.
-- Installed via automation/install-folder-action.sh, which substitutes
-- __WHISP_HELPER__ (the shared serialized-transcribe helper, see lib.sh /
-- whisp-transcribe.sh) and compiles this into a .scpt with osacompile —
-- Folder Actions are compiled AppleScript, not shell scripts or Automator
-- workflows.
--
-- Output goes to a "Transcripts" subfolder of the watched folder, not the
-- watched folder itself: writing the .txt/.srt output back into the folder
-- being watched would itself count as a new item and re-fire this handler
-- (harmlessly, since text files aren't audio — but wastefully). The
-- install script pre-creates that subfolder so its first-ever creation
-- can't itself trigger this handler either.
--
-- Runs through whisp-transcribe.sh rather than calling whisp directly, so
-- that dropping several files within minutes of each other queues them
-- instead of running multiple whisp processes (each loading its own copy
-- of the model into GPU memory) at once.
--
-- To change the whisp flags used (e.g. drop --srt, add --language fr), edit
-- the shellCmd line below and re-run the install script.
on adding folder items to thisFolder after receiving addedItems
	set outDir to (POSIX path of thisFolder) & "Transcripts"
	repeat with anItem in addedItems
		set posixPath to POSIX path of anItem
		set shellCmd to "\"__WHISP_HELPER__\" " & quoted form of posixPath & " -- --srt --quiet --output-dir " & quoted form of outDir & " >/dev/null 2>&1; osascript -e 'display notification \"Transcription finished\" with title \"Whisp\"' >/dev/null 2>&1 &"
		do shell script shellCmd
	end repeat
end adding folder items to
