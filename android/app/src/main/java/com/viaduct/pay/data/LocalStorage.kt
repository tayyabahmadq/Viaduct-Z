package com.viaduct.pay.data

import android.content.Context
import android.content.SharedPreferences
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * Device-local state: server URL, the signed-in account, and the offline outbox.
 *
 * To point the app at your deployment, change [DEFAULT_SERVER_URL] to
 * "https://viaduct-ledger.onrender.com" (or set it at runtime in Profile).
 */
object LocalStorage {

    const val DEFAULT_SERVER_URL: String = "http://10.0.2.2:8000"

    private const val PREFS = "viaduct_session"
    private const val KEY_URL = "base_url"
    private const val KEY_ACCOUNT = "account"
    private const val KEY_OUTBOX = "outbox"

    private lateinit var prefs: SharedPreferences
    private val json = Json { ignoreUnknownKeys = true }

    fun init(context: Context) {
        prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    }

    var baseUrl: String
        get() {
            val raw = prefs.getString(KEY_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
            val trimmed = raw.trim().ifBlank { DEFAULT_SERVER_URL }
            return if (trimmed.endsWith("/")) trimmed else "$trimmed/"
        }
        set(value) {
            val normalized = value.trim().ifBlank { DEFAULT_SERVER_URL }
            prefs.edit().putString(KEY_URL, normalized).apply()
            Api.reset()
        }

    var account: AccountDto?
        get() = prefs.getString(KEY_ACCOUNT, null)
            ?.let { runCatching { json.decodeFromString<AccountDto>(it) }.getOrNull() }
        set(value) {
            prefs.edit().putString(KEY_ACCOUNT, value?.let { json.encodeToString(it) }).apply()
            Api.reset()
        }

    val token: String? get() = account?.token

    fun enqueue(item: PaymentRequest) {
        val list = outbox().toMutableList()
        list.add(item)
        prefs.edit().putString(KEY_OUTBOX, json.encodeToString(list)).apply()
    }

    fun outbox(): List<PaymentRequest> =
        prefs.getString(KEY_OUTBOX, null)
            ?.let { runCatching { json.decodeFromString<List<PaymentRequest>>(it) }.getOrNull() }
            ?: emptyList()

    fun clearOutbox() {
        prefs.edit().remove(KEY_OUTBOX).apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
        Api.reset()
    }
}
