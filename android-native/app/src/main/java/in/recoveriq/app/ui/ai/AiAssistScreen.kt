package `in`.recoveriq.app.ui.ai

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import `in`.recoveriq.app.data.User
import `in`.recoveriq.app.ui.AuthViewModel
import `in`.recoveriq.app.ui.theme.BrandBlue
import `in`.recoveriq.app.ui.theme.CardWhite
import `in`.recoveriq.app.ui.theme.GlassStroke
import `in`.recoveriq.app.ui.theme.Muted
import `in`.recoveriq.app.ui.theme.TextDark
import kotlinx.coroutines.launch

private data class Msg(val text: String, val fromUser: Boolean)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AiAssistScreen(vm: AuthViewModel, user: User, onBack: () -> Unit) {
    val messages = remember {
        mutableStateListOf(
            Msg("Hi ${user.name.substringBefore(' ')} — I'm your RecoverIQ assistant. " +
                "Ask me about your cases, what to do next, or how anything in the app works.", false)
        )
    }
    var input by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()

    fun send() {
        val q = input.trim()
        if (q.isBlank() || busy) return
        messages.add(Msg(q, true))
        input = ""; busy = true
        scope.launch {
            val reply = runCatching { vm.repo.aiAssist(q) }
                .getOrElse { "I couldn't reach the assistant just now. Please try again." }
            messages.add(Msg(reply, false))
            busy = false
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    Scaffold(
        containerColor = androidx.compose.ui.graphics.Color.Transparent,
        topBar = {
            TopAppBar(
                title = { Text("AI Assist") },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = androidx.compose.ui.graphics.Color(0xF2FFFFFF),
                    titleContentColor = BrandBlue,
                    navigationIconContentColor = BrandBlue,
                ),
            )
        },
        bottomBar = {
            Surface(color = CardWhite, shadowElevation = 8.dp) {
                Row(
                    Modifier.fillMaxWidth().padding(10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    OutlinedTextField(
                        value = input, onValueChange = { input = it },
                        placeholder = { Text("Ask anything…") },
                        modifier = Modifier.weight(1f),
                        keyboardOptions = KeyboardOptions(),
                        maxLines = 4,
                    )
                    IconButton(onClick = { send() }, enabled = !busy && input.isNotBlank()) {
                        Icon(Icons.AutoMirrored.Filled.Send, "Send", tint = BrandBlue)
                    }
                }
            }
        },
    ) { pad ->
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(pad).padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 12.dp),
        ) {
            items(messages.size) { i -> Bubble(messages[i]) }
            if (busy) item { TypingBubble() }
        }
    }
}

@Composable
private fun Bubble(msg: Msg) {
    val bg = if (msg.fromUser) BrandBlue else CardWhite
    val fg = if (msg.fromUser) androidx.compose.ui.graphics.Color.White else TextDark
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (msg.fromUser) Arrangement.End else Arrangement.Start) {
        Surface(
            color = bg,
            contentColor = fg,
            shape = RoundedCornerShape(14.dp),
            border = if (msg.fromUser) null else BorderStroke(1.dp, GlassStroke),
            shadowElevation = if (msg.fromUser) 0.dp else 2.dp,
            modifier = Modifier.widthIn(max = 300.dp),
        ) {
            Text(msg.text, color = fg, style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp))
        }
    }
}

@Composable
private fun TypingBubble() {
    Row(horizontalArrangement = Arrangement.Start) {
        Surface(color = CardWhite, shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, GlassStroke), shadowElevation = 2.dp) {
            Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
                Text("Thinking…", color = Muted, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
