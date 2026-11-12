package com.viaduct.pay.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query
import java.util.concurrent.TimeUnit

/* ------------------------------- wire types ------------------------------ */

@Serializable
data class RegisterRequest(
    val device_id: String? = null,
    val name: String? = null
)

@Serializable
data class AccountDto(
    val device_id: String,
    val name: String,
    val token: String,
    val token48: String,
    val balance_cents: Int,
    val credit_ceiling_cents: Int,
    val seq: Int,
    val created_at: String
)

@Serializable
data class PeerDto(
    val device_id: String,
    val name: String,
    val token48: String,
    val online: Boolean,
    val last_seen_at: String
)

@Serializable
data class PaymentRequest(
    val to_token48: String,
    val amount_cents: Int,
    val memo: String? = null,
    val idempotency_key: String
)

@Serializable
data class ReceiptDto(
    val status: String,
    val transaction_id: String,
    val amount_cents: Int,
    val token48: String? = null,
    val sender_balance: Int,
    val receiver_balance: Int,
    val reason_code: String? = null
)

@Serializable
data class HistoryItemDto(
    val transaction_id: String,
    val direction: String,
    val counterparty: String,
    val counterparty_token48: String,
    val amount_cents: Int,
    val status: String,
    val memo: String? = null,
    val created_at: String
)

@Serializable
data class BatchRequest(val items: List<PaymentRequest>)

@Serializable
data class BatchItemResult(
    val transaction_id: String,
    val status: String,
    val reason_code: String? = null
)

@Serializable
data class BatchResponse(
    val accepted: List<BatchItemResult>,
    val declined: List<BatchItemResult>
)

@Serializable
data class TokenVerifyRequest(val token48: String)

@Serializable
data class TokenVerifyResponse(
    val valid: Boolean,
    val reason: String,
    val parts: kotlinx.serialization.json.JsonObject? = null
)

@Serializable
data class PayPalOrderRequest(val amount_cents: Int)

@Serializable
data class PayPalOrderDto(
    val order_id: String,
    val approve_url: String? = null,
    val amount_cents: Int,
    val currency: String,
    val status: String = "CREATED"
)

@Serializable
data class PayPalCaptureRequest(val order_id: String)

@Serializable
data class PayPalCaptureDto(
    val status: String,
    val order_id: String,
    val capture_id: String? = null,
    val amount_cents: Int,
    val balance_cents: Int,
    val reason_code: String? = null
)

@Serializable
data class AssistantRequest(val text: String)

@Serializable
data class AssistantDto(
    val action: String,
    val receiver_name: String? = null,
    val token48: String? = null,
    val amount_cents: Int? = null,
    val memo: String? = null,
    val confidence: Double = 0.0,
    val source: String = "rules",
    val explanation: String = ""
)

/* --------------------------------- client -------------------------------- */

interface ViaductApi {
    @POST("api/v1/devices/register")
    suspend fun register(@Body body: RegisterRequest): AccountDto

    @GET("api/v1/me")
    suspend fun me(): AccountDto

    @GET("api/v1/peers")
    suspend fun peers(@Query("q") q: String? = null): List<PeerDto>

    @GET("api/v1/peers/resolve")
    suspend fun resolve(@Query("token48") token48: String): PeerDto

    @POST("api/v1/payments")
    suspend fun pay(@Body body: PaymentRequest): ReceiptDto

    @GET("api/v1/payments")
    suspend fun history(
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0
    ): List<HistoryItemDto>

    @POST("api/v1/payments/batch-sync")
    suspend fun batchSync(@Body body: BatchRequest): BatchResponse

    @POST("api/v1/tokens/verify")
    suspend fun verifyToken(@Body body: TokenVerifyRequest): TokenVerifyResponse

    @POST("api/v1/topups/paypal/order")
    suspend fun createPayPalOrder(@Body body: PayPalOrderRequest): PayPalOrderDto

    @POST("api/v1/topups/paypal/capture")
    suspend fun capturePayPalOrder(@Body body: PayPalCaptureRequest): PayPalCaptureDto

    @POST("api/v1/assistant/parse")
    suspend fun parseIntent(@Body body: AssistantRequest): AssistantDto
}

object Api {
    @Volatile
    private var instance: ViaductApi? = null

    fun get(): ViaductApi {
        instance?.let { return it }
        return synchronized(this) {
            instance ?: build().also { instance = it }
        }
    }

    fun reset() {
        instance = null
    }

    private fun build(): ViaductApi {
        val client = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                val builder = chain.request().newBuilder()
                LocalStorage.token?.let { builder.header("Authorization", "Bearer $it") }
                chain.proceed(builder.build())
            }
            .build()

        val json = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
            coerceInputValues = true
        }

        return Retrofit.Builder()
            .baseUrl(LocalStorage.baseUrl)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(ViaductApi::class.java)
    }
}
