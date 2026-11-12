@file:OptIn(ExperimentalMaterial3Api::class)

package com.viaduct.pay.ui

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.viaduct.pay.data.Api
import com.viaduct.pay.data.AssistantDto
import com.viaduct.pay.data.AssistantRequest
import kotlinx.coroutines.launch

/* ------------------------------------------------------------------ */
/* AI assistant                                                        */
/* ------------------------------------------------------------------ */

@Composable
fun AssistantScreen(nav: NavController) {
    val scope = rememberCoroutineScope()
    var request by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var parsed by remember { mutableStateOf<AssistantDto?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("AI assistant") },
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
            Text(
                "Describe a payment in plain English. The server turns it into an instruction — " +
                    "nothing is sent until you continue.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            OutlinedTextField(
                value = request,
                onValueChange = { request = it.take(200) },
                label = { Text("Request") },
                placeholder = { Text("send $25 to Mei Chen") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )

            Button(
                onClick = {
                    busy = true
                    error = null
                    parsed = null
                    scope.launch {
                        try {
                            parsed = Api.get().parseIntent(AssistantRequest(text = request.trim()))
                        } catch (e: Exception) {
                            error = e.message ?: "Could not reach the server"
                        } finally {
                            busy = false
                        }
                    }
                },
                enabled = request.isNotBlank() && !busy,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(if (busy) "Parsing…" else "Parse")
            }

            val result = parsed
            if (result != null) {
                AssistantResultCard(result)

                val token = result.token48
                val amount = result.amount_cents
                if (result.action == "PAY" && token != null && amount != null) {
                    Button(
                        onClick = {
                            nav.navigate(
                                "send/$token/${Uri.encode(result.receiver_name ?: "Peer")}?amount=$amount"
                            )
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) { Text("Continue") }
                } else if (result.action == "PAY") {
                    Text(
                        "This request has no receiver token or amount, so it cannot be sent.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
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
private fun AssistantResultCard(dto: AssistantDto) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    dto.action,
                    style = MaterialTheme.typography.titleMedium,
                    color = if (dto.action == "PAY") {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.onSurface
                    }
                )
                Text(
                    "${(dto.confidence * 100).toInt()}% confident",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Text("To: " + (dto.receiver_name ?: "—"))
            Text("Amount: " + (dto.amount_cents?.let { "$" + money(it) } ?: "—"))
            if (dto.token48 != null) {
                Text(
                    "Token: ${dto.token48.take(6)}…",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Text(
                "Source: " + dto.source,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(dto.explanation, style = MaterialTheme.typography.bodySmall)
        }
    }
}
