package com.remotecontrol.app

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat

/** PCの画面を全画面で表示して操作する画面。中身はPCアプリが配信するページ。 */
class RemoteActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private var dialog: AlertDialog? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        web = WebView(this)
        setContentView(web)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError,
            ) {
                if (request.isForMainFrame) showError(error.description.toString())
            }
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = showMenu()
        })

        load()
    }

    override fun onResume() {
        super.onResume()
        hideSystemBars()
    }

    override fun onDestroy() {
        dialog?.dismiss()
        web.destroy()
        super.onDestroy()
    }

    private fun load() {
        val url = Prefs.url(this)
        if (url == null) {
            editConnection()
            return
        }
        web.loadUrl(url)
    }

    private fun hideSystemBars() {
        val c = WindowInsetsControllerCompat(window, window.decorView)
        c.hide(WindowInsetsCompat.Type.systemBars())
        c.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
    }

    private fun showMenu() {
        val items = arrayOf(
            getString(R.string.menu_reload),
            getString(R.string.menu_change),
            getString(R.string.menu_exit),
        )
        show(
            AlertDialog.Builder(this)
                .setItems(items) { _, which ->
                    when (which) {
                        0 -> web.reload()
                        1 -> editConnection()
                        else -> finish()
                    }
                }
        )
    }

    private fun showError(detail: String) {
        show(
            AlertDialog.Builder(this)
                .setTitle(R.string.error_title)
                .setMessage(getString(R.string.error_message, detail))
                .setCancelable(false)
                .setPositiveButton(R.string.retry) { _, _ -> load() }
                .setNegativeButton(R.string.menu_change) { _, _ -> editConnection() }
        )
    }

    private fun show(builder: AlertDialog.Builder) {
        if (isFinishing) return
        dialog?.dismiss()
        dialog = builder.setOnDismissListener { hideSystemBars() }.show()
    }

    private fun editConnection() {
        startActivity(Intent(this, MainActivity::class.java).putExtra(MainActivity.EXTRA_EDIT, true))
        finish()
    }
}
