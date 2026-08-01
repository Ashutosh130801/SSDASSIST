package `in`.recoveriq.app

import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File

/**
 * Self-update for the sideloaded app. On launch it asks the backend
 * (`<BASE_URL>/downloads/version.json`) for the latest published build; if that version code
 * is higher than this install's, it prompts the user, downloads the APK from the same server,
 * and opens Android's installer (one confirmation tap — the only fully-silent path is MDM).
 */
object Updater {
    data class Info(val versionCode: Int, val versionName: String, val url: String, val notes: String)

    private val client = OkHttpClient()

    /** Returns update info if the server has a newer build than this one, else null. */
    suspend fun check(): Info? = withContext(Dispatchers.IO) {
        try {
            val base = BuildConfig.BASE_URL.trimEnd('/')
            val req = Request.Builder()
                .url("$base/downloads/version.json")
                .addHeader("ngrok-skip-browser-warning", "true")
                .build()
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return@withContext null
                val body = resp.body?.string() ?: return@withContext null
                val j = JSONObject(body)
                val vc = j.optInt("version_code", 0)
                if (vc <= BuildConfig.VERSION_CODE) return@withContext null
                Info(
                    versionCode = vc,
                    versionName = j.optString("version_name", ""),
                    url = j.optString("url", "").ifBlank { "$base/downloads/RecoverIQ-native.apk" },
                    notes = j.optString("notes", ""),
                )
            }
        } catch (e: Exception) {
            null
        }
    }

    /** Download the new APK via the system DownloadManager, then launch the installer. */
    fun downloadAndInstall(context: Context, url: String) {
        val ctx = context.applicationContext
        val dm = ctx.getSystemService(Context.DOWNLOAD_SERVICE) as DownloadManager
        // Reuse a stable filename in the app's external files dir (covered by fileprovider).
        val name = "RecoverIQ-update.apk"
        File(ctx.getExternalFilesDir(null), name).takeIf { it.exists() }?.delete()
        val req = DownloadManager.Request(Uri.parse(url))
            .setTitle("Updating RecoverIQ")
            .setDescription("Downloading the new version…")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setMimeType("application/vnd.android.package-archive")
            .setDestinationInExternalFilesDir(ctx, null, name)
        val id = dm.enqueue(req)
        Toast.makeText(ctx, "Downloading update…", Toast.LENGTH_SHORT).show()

        Thread {
            var finished = false
            while (!finished) {
                val q = DownloadManager.Query().setFilterById(id)
                dm.query(q)?.use { c ->
                    if (c.moveToFirst()) {
                        val status = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
                        if (status == DownloadManager.STATUS_SUCCESSFUL) {
                            finished = true
                            val file = File(ctx.getExternalFilesDir(null), name)
                            Handler(Looper.getMainLooper()).post { install(ctx, file) }
                        } else if (status == DownloadManager.STATUS_FAILED) {
                            finished = true
                            Handler(Looper.getMainLooper()).post {
                                Toast.makeText(ctx, "Update download failed. Try again later.", Toast.LENGTH_LONG).show()
                            }
                        }
                    }
                }
                if (!finished) Thread.sleep(700)
            }
        }.start()
    }

    private fun install(context: Context, file: File) {
        if (!file.exists()) return
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        runCatching { context.startActivity(intent) }
    }
}

/** Drop this near the top of the signed-in UI: it checks once and shows an update prompt. */
@Composable
fun UpdateGate() {
    val context = LocalContext.current
    var info by remember { mutableStateOf<Updater.Info?>(null) }
    var dismissed by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { info = Updater.check() }

    val i = info
    if (i != null && !dismissed) {
        AlertDialog(
            onDismissRequest = { dismissed = true },
            title = { Text("Update available") },
            text = {
                Text(
                    "A new version (${i.versionName.ifBlank { "v${i.versionCode}" }}) is ready." +
                        if (i.notes.isNotBlank()) "\n\n${i.notes}" else "",
                )
            },
            confirmButton = {
                TextButton(onClick = { dismissed = true; Updater.downloadAndInstall(context, i.url) }) {
                    Text("Update")
                }
            },
            dismissButton = { TextButton(onClick = { dismissed = true }) { Text("Later") } },
        )
    }
}
