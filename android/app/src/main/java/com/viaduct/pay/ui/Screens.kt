@file:OptIn(ExperimentalMaterial3Api::class)

package com.viaduct.pay.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanIntentResult
import com.journeyapps.barcodescanner.ScanOptions
import com.viaduct.pay.data.AccountDto
import com.viaduct.pay.data.Api
import com.viaduct.pay.data.BatchRequest
import com.viaduct.pay.data.HistoryItemDto
import com.viaduct.pay.data.LocalStorage
import com.viaduct.pay.data.PaymentRequest
import com.viaduct.pay.data.PeerDto
import com.viaduct.pay.data.ReceiptDto
import com.viaduct.pay.data.RegisterRequest
import com.viaduct.pay.utils.AccountState
import com.viaduct.pay.utils.TxDraft
import com.viaduct.pay.utils.TxGuard
import kotlinx.coroutines.launch
import java.util.UUID

private val Positive = Color(0xFF10B981)

/* ------------------------------------------------------------------ */
/* Register                                                            */
/* ------------------------------------------------------------------ */

@Composable
fun RegisterScreen(nav: NavController) {
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Text("Viaduct Pay", style = MaterialTheme.typography.headlineMedium)
        Spacer(Modifier.height(6.dp))
        Text(
            "Demo wallet. No KYC, no real money — every transfer settles against the API in this repo.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(Modifier.height(28.dp))

        OutlinedTextField(
            value = name,
            onValueChange = { name = it.take(64) },
            label = { Text("Display name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(16.dp))

        Button(
            onClick = {
                busy = true
                error = null
                scope.launch {
                    try {
                        val account = Api.get().register(
                            RegisterRequest(
                                device_id = UUID.randomUUID().toString(),
                                name = name.ifBlank { null }
                            )
                        )
                        LocalStorage.account = account
                        nav.navigate("home") {
                            popUpTo("register") { inclusive = true }
                        }
                    } catch (e: Exception) {
                        error = e.message ?: "Could not reach the server"
                    } finally {
                        busy = false
                    }
                }
            },
            enabled = !busy,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (busy) "Creating…" else "Create demo account")
        }

        if (error != null) {
            Spacer(Modifier.height(12.dp))
            Text(
                error!!,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall
            )
        }

        Spacer(Modifier.height(20.dp))
        Text(
            "Server: ${LocalStorage.baseUrl}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

/* ------------------------------------------------------------------ */
/* Home                                                                */
/* ------------------------------------------------------------------ */

@Composable
fun HomeScreen(nav: NavController) {
    var account by remember { mutableStateOf(LocalStorage.account) }
    var rows by remember { mutableStateOf<List<HistoryItemDto>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableStateOf(0) }

    LaunchedEffect(reload) {
        error = null
        try {
            val fresh = Api.get().me()
            account = fresh
            LocalStorage.account = fresh

            val queued = LocalStorage.outbox()
            if (queued.isNotEmpty()) {
                val result = Api.get().batchSync(BatchRequest(queued))
                LocalStorage.clearOutbox()
                error = "${result.accepted.size} queued payment(s) settled, ${result.declined.size} declined"
                account = Api.get().me()
                LocalStorage.account = account
            }
            rows = Api.get().history(5)
        } catch (e: Exception) {
            error = e.message ?: "Network error"
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Viaduct Pay") },
                actions = {
                    IconButton(onClick = { reload++ }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                    IconButton(onClick = { nav.navigate("profile") }) {
                        Icon(Icons.Default.Person, contentDescription = "Profile")
                    }
                }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp)) {
                        Text(
                            "TOTAL BALANCE",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(Modifier.height(6.dp))
                        Text(
                            text = account?.let { "$" + money(it.balance_cents) } ?: "—",
                            style = MaterialTheme.typography.displaySmall
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = account?.let { "Ceiling per transfer: $" + money(it.credit_ceiling_cents) }
                                ?: "",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }

            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = { nav.navigate("scan") },
                        modifier = Modifier.weight(1f)
                    ) { Text("Scan") }
                    Button(
                        onClick = { nav.navigate("history") },
                        modifier = Modifier.weight(1f)
                    ) { Text("Activity") }
                }
            }

            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = { nav.navigate("topup") },
                        modifier = Modifier.weight(1f)
                    ) { Text("Top up") }
                    OutlinedButton(
                        onClick = { nav.navigate("assistant") },
                        modifier = Modifier.weight(1f)
                    ) { Text("AI assistant") }
                }
            }

            item { Text("Recent activity", style = MaterialTheme.typography.titleMedium) }

            if (rows.isEmpty()) {
                item {
                    Text(
                        "No payments yet. Scan a QR code or paste a peer token.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            items(rows) { TransactionRow(it) }

            if (error != null) {
                item {
                    Text(
                        error!!,
                        color = MaterialTheme.colorScheme.error,
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }
        }
    }
}

@Composable
fun TransactionRow(item: HistoryItemDto) {
    val incoming = item.direction == "IN"
    ListItem(
        headlineContent = { Text(item.counterparty) },
        supportingContent = { Text(item.created_at.replace("T", " ").take(16)) },
        trailingContent = {
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = (if (incoming) "+" else "−") + "$" + money(item.amount_cents),
                    color = if (incoming) Positive else MaterialTheme.colorScheme.onSurface
                )
                Text(
                    text = item.status,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    )
}

/* ------------------------------------------------------------------ */
/* Scan                                                                */
/* ------------------------------------------------------------------ */

@Composable
fun ScanScreen(nav: NavController) {
    val scope = rememberCoroutineScope()
    var manual by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var peers by remember { mutableStateOf<List<PeerDto>>(emptyList()) }

    LaunchedEffect(Unit) {
        peers = runCatching { Api.get().peers() }.getOrDefault(emptyList())
    }

    fun go(raw: String) {
        val token = raw.trim()
        if (token.length != 48 || !token.all { it.isDigit() }) {
            error = "A Viaduct token is exactly 48 digits."
            return
        }
        error = null
        scope.launch {
            val peer = runCatching { Api.get().resolve(token) }.getOrNull()
            nav.navigate("send/$token/${Uri.encode(peer?.name ?: "Scanned peer")}")
        }
    }

    val scanner = rememberLauncherForActivityResult(ScanContract()) { result: ScanIntentResult ->
        val contents = result.contents
        if (contents != null) go(contents) else error = "Scan cancelled"
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Scan & pay") },
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
                        "Point the camera at a Viaduct QR code.",
                        style = MaterialTheme.typography.bodyMedium
                    )
                    Spacer(Modifier.height(12.dp))
                    Button(onClick = {
                        scanner.launch(
                            ScanOptions().apply {
                                setPrompt("Align the QR code in the frame")
                                setBeepEnabled(false)
                            }
                        )
                    }) { Text("Open camera") }
                }
            }

            Text("or paste a token", style = MaterialTheme.typography.titleSmall)

            OutlinedTextField(
                value = manual,
                onValueChange = { manual = it.filter(Char::isDigit).take(48) },
                label = { Text("48-digit token") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )

            Button(
                onClick = { go(manual) },
                enabled = manual.length == 48,
                modifier = Modifier.fillMaxWidth()
            ) { Text("Continue") }

            if (error != null) {
                Text(
                    error!!,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall
                )
            }

            if (peers.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text("or pick a wallet", style = MaterialTheme.typography.titleSmall)
                peers.take(10).forEach { peer ->
                    ListItem(
                        headlineContent = { Text(peer.name) },
                        supportingContent = {
                            Text(if (peer.online) "online" else "offline")
                        },
                        trailingContent = {
                            Text(
                                peer.token48.take(6) + "…",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        },
                        modifier = Modifier.clickable {
                            nav.navigate("send/${peer.token48}/${Uri.encode(peer.name)}")
                        }
                    )
                }
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* Send                                                                */
/* ------------------------------------------------------------------ */

@Composable
fun SendScreen(
    nav: NavController,
    token48: String,
    label: String,
    initialAmountCents: Int = 0
) {
    val scope = rememberCoroutineScope()
    var digits by remember {
        mutableStateOf(if (initialAmountCents > 0) initialAmountCents.toString() else "")
    }
    var memo by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var receipt by remember { mutableStateOf<ReceiptDto?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var account by remember { mutableStateOf(LocalStorage.account) }

    val amountCents = digits.trimStart('0').toIntOrNull() ?: 0

    LaunchedEffect(Unit) {
        runCatching { Api.get().me() }.onSuccess {
            account = it
            LocalStorage.account = it
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Send money") },
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
            Text(label.ifBlank { "Recipient" }, style = MaterialTheme.typography.titleMedium)
            Text(
                token48.chunked(4).joinToString(" "),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text("$" + money(amountCents), style = MaterialTheme.typography.displaySmall)
                }
            }

            OutlinedTextField(
                value = memo,
                onValueChange = { memo = it.take(140) },
                label = { Text("Note (optional)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )

            Keypad(
                onDigit = { ch -> if (digits.length < 8) digits += ch },
                onBackspace = { digits = digits.dropLast(1) }
            )

            if (receipt == null) {
                Button(
                    onClick = {
                        val current = account
                        val decision = if (current == null) {
                            null
                        } else {
                            TxGuard.screen(
                                TxDraft(
                                    sender_account_id = current.device_id,
                                    receiver_account_id = token48,
                                    amount = amountCents,
                                    nonce = UUID.randomUUID().toString(),
                                    token48 = null,
                                    timestamp_ms = System.currentTimeMillis()
                                ),
                                AccountState(
                                    account_id = current.device_id,
                                    balance = current.balance_cents,
                                    credit_ceiling = current.credit_ceiling_cents,
                                    seq = current.seq
                                )
                            )
                        }

                        if (decision != null && decision.decision == "DENY") {
                            error = "${decision.code}: ${decision.reason}"
                        } else {
                            busy = true
                            error = null
                            val request = PaymentRequest(
                                to_token48 = token48,
                                amount_cents = amountCents,
                                memo = memo.ifBlank { null },
                                idempotency_key = UUID.randomUUID().toString()
                            )
                            scope.launch {
                                try {
                                    receipt = Api.get().pay(request)
                                } catch (e: Exception) {
                                    LocalStorage.enqueue(request)
                                    error = "Server unreachable — payment queued on this device."
                                } finally {
                                    busy = false
                                }
                            }
                        }
                    },
                    enabled = amountCents > 0 && !busy,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(if (busy) "Sending…" else "Send $" + money(amountCents))
                }
            } else {
                ReceiptCard(receipt!!)
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
private fun Keypad(onDigit: (Char) -> Unit, onBackspace: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf("123", "456", "789").forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                row.forEach { ch ->
                    Button(
                        onClick = { onDigit(ch) },
                        modifier = Modifier.weight(1f)
                    ) {
                        Text(ch.toString(), style = MaterialTheme.typography.titleLarge)
                    }
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { onDigit('0') }, modifier = Modifier.weight(1f)) {
                Text("0", style = MaterialTheme.typography.titleLarge)
            }
            Button(onClick = onBackspace, modifier = Modifier.weight(1f)) { Text("⌫") }
        }
    }
}

@Composable
private fun ReceiptCard(receipt: ReceiptDto) {
    val completed = receipt.status == "COMPLETED"
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(
                if (completed) "Payment completed" else "Payment declined",
                style = MaterialTheme.typography.titleMedium,
                color = if (completed) Positive else MaterialTheme.colorScheme.error
            )
            Text("$" + money(receipt.amount_cents))
            Text(
                "Your balance: $" + money(receipt.sender_balance),
                style = MaterialTheme.typography.bodySmall
            )
            if (receipt.reason_code != null) {
                Text("Reason: ${receipt.reason_code}", style = MaterialTheme.typography.bodySmall)
            }
            Text(
                "Ref: ${receipt.transaction_id.take(8)}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (receipt.token48 != null) {
                Text(
                    "Receipt token: ${receipt.token48.take(12)}…",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* History                                                             */
/* ------------------------------------------------------------------ */

@Composable
fun HistoryScreen(nav: NavController) {
    var rows by remember { mutableStateOf<List<HistoryItemDto>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableStateOf(0) }

    LaunchedEffect(reload) {
        try {
            rows = Api.get().history(100)
        } catch (e: Exception) {
            error = e.message ?: "Network error"
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Activity") },
                navigationIcon = {
                    IconButton(onClick = { nav.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { reload++ }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                }
            )
        }
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(16.dp)
        ) {
            if (rows.isEmpty()) {
                item {
                    Text(
                        "No transactions yet.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            items(rows) { TransactionRow(it) }
            if (error != null) {
                item { Text(error!!, color = MaterialTheme.colorScheme.error) }
            }
        }
    }
}

/* ------------------------------------------------------------------ */
/* Profile                                                             */
/* ------------------------------------------------------------------ */

@Composable
fun ProfileScreen(nav: NavController) {
    var account by remember { mutableStateOf<AccountDto?>(LocalStorage.account) }
    var baseUrl by remember { mutableStateOf(LocalStorage.baseUrl) }
    var message by remember { mutableStateOf<String?>(null) }
    val clipboard = LocalClipboardManager.current

    LaunchedEffect(Unit) {
        runCatching { Api.get().me() }.onSuccess {
            account = it
            LocalStorage.account = it
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Profile") },
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
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            val acc = account
            if (acc != null) {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Text(acc.name, style = MaterialTheme.typography.titleLarge)
                        Text("Balance: $" + money(acc.balance_cents))
                        Text("Ceiling: $" + money(acc.credit_ceiling_cents))
                        Text("Seq: ${acc.seq}")
                    }
                }

                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text("Your receive QR", style = MaterialTheme.typography.titleMedium)
                        Spacer(Modifier.height(12.dp))
                        Image(
                            bitmap = remember(acc.token48) { Qr.bitmap(acc.token48, 512) }
                                .asImageBitmap(),
                            contentDescription = "Receive QR",
                            modifier = Modifier.size(220.dp)
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            acc.token48.chunked(4).joinToString(" "),
                            style = MaterialTheme.typography.labelSmall
                        )
                        TextButton(onClick = {
                            clipboard.setText(AnnotatedString(acc.token48))
                            message = "Token copied."
                        }) { Text("Copy token") }
                    }
                }
            } else {
                Text("Not signed in.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text("Server", style = MaterialTheme.typography.titleMedium)
                    OutlinedTextField(
                        value = baseUrl,
                        onValueChange = { baseUrl = it },
                        label = { Text("Base URL") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Button(
                        onClick = {
                            LocalStorage.baseUrl = baseUrl
                            baseUrl = LocalStorage.baseUrl
                            message = "Saved. New requests use this server."
                        },
                        modifier = Modifier.fillMaxWidth()
                    ) { Text("Save server URL") }
                }
            }

            if (message != null) {
                Text(
                    message!!,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Button(
                onClick = { nav.navigate("topup") },
                modifier = Modifier.fillMaxWidth()
            ) { Text("Top up with PayPal") }

            OutlinedButton(
                onClick = {
                    LocalStorage.clear()
                    nav.navigate("register") { popUpTo(0) { inclusive = true } }
                },
                modifier = Modifier.fillMaxWidth()
            ) { Text("Sign out") }
        }
    }
}
