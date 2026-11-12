@file:OptIn(ExperimentalMaterial3Api::class)

package com.viaduct.pay.ui

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.viaduct.pay.data.Api
import com.viaduct.pay.data.PayPalCaptureDto
import com.viaduct.pay.data.PayPalCaptureRequest
import com.viaduct.pay.data.PayPalOrderDto
import com.viaduct.pay.data.PayPalOrderRequest
import kotlinx.coroutines.launch

private val PositiveColor = Color(0xFF10B981)

private val TopUpPresets = listOf(1000 to "$10", 2500 to "$25", 5000 to "$50")

/* ------------------------------------------------------------------ */
/* Top up                                                              */
/* ------------------------------------------------------------------ */

@Composable
fun TopUpScreen(nav: NavController) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    var amountCents by remember { mutableStateOf(2500) }
    var order by remember { mutableStateOf<PayPalOrderDto?>(null) }
    var capture by remember { mutableStateOf<PayPalCaptureDto?>(null) }
    var creating by remember { mutableStateOf(false) }
    var capturing by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    val busy = creating || capturing

    fun select(cents: Int) {
        amountCents = cents
        order = null
        error = null
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Top up") },
                navigationIcon = {
                    IconButton(onClick = { nav.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        "TOP UP AMOUNT",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.height(6.dp))
                    Text("$" + money(amountCents), style = MaterialTheme.typography.displaySmall)
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                TopUpPresets.forEach { (cents, label) ->
                    if (cents == amountCents) {
                        Button(
                            onClick = { select(cents) },
                            enabled = !busy,
                            modifier = Modifier.weight(1f)
                        ) { Text(label) }
                    } else {
                        OutlinedButton(
                            onClick = { select(cents) },
                            enabled = !busy,
                            modifier = Modifier.weight(1f)
                        ) { Text(label) }
                    }
                }
            }

            Text(
                "Pay with PayPal, then capture the order here to credit your balance.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            val pending = order

            if (pending != null && capture == null) {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Text("PayPal order created", style = MaterialTheme.typography.titleMedium)
                        Text(
                            "Order: ${pending.order_id}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text("$" + money(pending.amount_cents) + " " + pending.currency)
                        if (pending.approve_url == null) {
                            Text(
                                "The server returned no approval link for this order.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.error
                            )
                        }
                    }
                }
            }

            if (capture == null) {
                Button(
                    onClick = {
                        val approvedUrl = order?.approve_url
                        if (approvedUrl != null) {
                            // Re-open the existing order instead of creating a second one.
                            if (!openInBrowser(context, approvedUrl)) {
                                error = "No app on this device can open the PayPal link."
                            }
                            return@Button
                        }

                        creating = true
                        error = null
                        scope.launch {
                            try {
                                val created = Api.get().createPayPalOrder(
                                    PayPalOrderRequest(amount_cents = amountCents)
                                )
                                order = created
                                val url = created.approve_url
                                if (url == null) {
                                    error = "The server returned no approval link."
                                } else if (!openInBrowser(context, url)) {
                                    error = "No app on this device can open the PayPal link."
                                }
                            } catch (e: Exception) {
                                error = e.message ?: "Could not reach the server"
                            } finally {
                                creating = false
                            }
                        }
                    },
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(if (creating) "Creating order…" else "Open PayPal")
                }

                if (pending != null) {
                    Button(
                        onClick = {
                            capturing = true
                            error = null
                            scope.launch {
                                try {
                                    capture = Api.get().capturePayPalOrder(
                                        PayPalCaptureRequest(order_id = pending.order_id)
                                    )
                                    order = null
                                } catch (e: Exception) {
                                    error = e.message ?: "Could not reach the server"
                                } finally {
                                    capturing = false
                                }
                            }
                        },
                        enabled = !busy,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(if (capturing) "Capturing…" else "I approved — capture")
                    }
                }
            } else {
                CaptureCard(capture!!)
                Button(
                    onClick = { nav.popBackStack() },
                    modifier = Modifier.fillMaxWidth()
                ) { Text("Done") }
            }

            if (error != null) {
                Text(
                    error!!,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}

@Composable
private fun CaptureCard(capture: PayPalCaptureDto) {
    val completed = capture.status == "COMPLETED"
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(
                if (completed) "Top-up complete" else "Top-up not completed",
                style = MaterialTheme.typography.titleMedium,
                color = if (completed) PositiveColor else MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text("Status: ${capture.status}", style = MaterialTheme.typography.bodySmall)
            Text("Credited: $" + money(capture.amount_cents))
            Text(
                "New balance: $" + money(capture.balance_cents),
                style = MaterialTheme.typography.bodySmall
            )
            Text(
                "Order: ${capture.order_id}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (capture.capture_id != null) {
                Text(
                    "Capture: ${capture.capture_id.take(12)}…",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/** Opens [url] in whatever app handles http(s). Returns false when nothing can. */
private fun openInBrowser(context: Context, url: String): Boolean =
    runCatching {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    }.isSuccess
