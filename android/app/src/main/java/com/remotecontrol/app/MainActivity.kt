package com.remotecontrol.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

/** 接続先の設定画面 (QRコード読み取り / URL入力)。設定済みならすぐ操作画面へ。 */
class MainActivity : AppCompatActivity() {

    private val scanner = registerForActivityResult(ScanContract()) { result ->
        result.contents?.let { onUrl(it.trim()) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val saved = Prefs.url(this)
        if (saved != null && !intent.getBooleanExtra(EXTRA_EDIT, false)) {
            openRemote()
            return
        }

        setContentView(R.layout.activity_main)
        val input = findViewById<EditText>(R.id.url_input)
        input.setText(saved ?: "")

        findViewById<Button>(R.id.scan_button).setOnClickListener {
            scanner.launch(
                ScanOptions()
                    .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                    .setPrompt(getString(R.string.scan_prompt))
                    .setBeepEnabled(false)
            )
        }
        findViewById<Button>(R.id.connect_button).setOnClickListener {
            onUrl(input.text.toString().trim())
        }
    }

    private fun onUrl(url: String) {
        if (!isValidUrl(url)) {
            Toast.makeText(this, R.string.invalid_url, Toast.LENGTH_LONG).show()
            return
        }
        Prefs.save(this, url)
        openRemote()
    }

    private fun openRemote() {
        startActivity(Intent(this, RemoteActivity::class.java))
        finish()
    }

    companion object {
        const val EXTRA_EDIT = "edit"

        /** PCアプリが表示する http://<IP>:<port>/#token=... 形式か確認する */
        fun isValidUrl(url: String): Boolean {
            val u = Uri.parse(url)
            return (u.scheme == "http" || u.scheme == "https") &&
                !u.host.isNullOrEmpty() &&
                (u.fragment ?: "").startsWith("token=")
        }
    }
}

object Prefs {
    private const val NAME = "remote_control"
    private const val KEY_URL = "url"

    fun url(ctx: Context): String? =
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).getString(KEY_URL, null)

    fun save(ctx: Context, url: String) {
        ctx.getSharedPreferences(NAME, Context.MODE_PRIVATE).edit().putString(KEY_URL, url).apply()
    }
}
