package org.dominionhealing.creator

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

private val DominionGold = Color(0xFFE0C06B)
private val DominionGoldDark = Color(0xFFC9A44D)
private val DominionInk = Color(0xFF0B0C0F)
private val DominionPanel = Color(0xFF15171D)
private val DominionPaper = Color(0xFFF4EFE5)
private val DominionMuted = Color(0xFFB9B5AC)

private val DominionScheme = darkColorScheme(
    primary = DominionGold,
    onPrimary = Color(0xFF111111),
    background = DominionInk,
    onBackground = DominionPaper,
    surface = DominionPanel,
    onSurface = DominionPaper,
    outline = Color(0xFF494C55),
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = DominionScheme) {
                DominionCreatorApp()
            }
        }
    }
}

private enum class AppScreen { HOME, BRIEF, ABOUT }

@Composable
private fun DominionCreatorApp() {
    var screenName by rememberSaveable { mutableStateOf(AppScreen.HOME.name) }
    val screen = AppScreen.valueOf(screenName)

    Scaffold(
        containerColor = DominionInk,
        bottomBar = {
            Surface(color = Color(0xFF101217), tonalElevation = 6.dp) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 8.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceEvenly,
                ) {
                    NavAction("Home", screen == AppScreen.HOME) { screenName = AppScreen.HOME.name }
                    NavAction("Creator brief", screen == AppScreen.BRIEF) { screenName = AppScreen.BRIEF.name }
                    NavAction("About", screen == AppScreen.ABOUT) { screenName = AppScreen.ABOUT.name }
                }
            }
        },
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .background(DominionInk),
        ) {
            when (screen) {
                AppScreen.HOME -> HomeScreen(onBuildBrief = { screenName = AppScreen.BRIEF.name })
                AppScreen.BRIEF -> CreatorBriefScreen()
                AppScreen.ABOUT -> AboutScreen()
            }
        }
    }
}

@Composable
private fun NavAction(label: String, selected: Boolean, onClick: () -> Unit) {
    TextButton(onClick = onClick) {
        Text(
            text = label,
            color = if (selected) DominionGold else DominionMuted,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
        )
    }
}

@Composable
private fun HomeScreen(onBuildBrief: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
    ) {
        Text(
            text = "DOMINION CREATOR",
            color = DominionGold,
            fontSize = 13.sp,
            fontWeight = FontWeight.ExtraBold,
            letterSpacing = 2.sp,
        )
        Spacer(Modifier.height(18.dp))
        Text(
            text = "Create with a system, not a scramble.",
            fontSize = 38.sp,
            lineHeight = 42.sp,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(14.dp))
        Text(
            text = "The first native beta gives creators a fast, phone-first way to turn an offer and audience into a focused campaign brief. Agent execution is added only after the public API and receipt gates are proven.",
            color = DominionMuted,
            fontSize = 17.sp,
            lineHeight = 25.sp,
        )
        Spacer(Modifier.height(28.dp))
        Button(
            onClick = onBuildBrief,
            colors = ButtonDefaults.buttonColors(containerColor = DominionGold),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Build a creator brief", fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(32.dp))
        StatusCard(
            title = "Native Android",
            detail = "Jetpack Compose · API 36 · no WebView wrapper",
            status = "ACTIVE BUILD",
        )
        StatusCard(
            title = "Governed execution",
            detail = "No publishing action is represented as complete without a backend receipt.",
            status = "FAIL CLOSED",
        )
        StatusCard(
            title = "Private control plane",
            detail = "Operator credentials and private Publisher routes are excluded from this consumer app.",
            status = "SEPARATED",
        )
    }
}

@Composable
private fun StatusCard(title: String, detail: String, status: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = DominionPanel),
        modifier = Modifier
            .fillMaxWidth()
            .padding(bottom = 12.dp),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(title, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text(status, color = DominionGold, fontSize = 11.sp, fontWeight = FontWeight.ExtraBold)
            }
            Spacer(Modifier.height(8.dp))
            Text(detail, color = DominionMuted, fontSize = 14.sp, lineHeight = 20.sp)
        }
    }
}

@Composable
private fun CreatorBriefScreen() {
    var offer by rememberSaveable { mutableStateOf("") }
    var audience by rememberSaveable { mutableStateOf("") }
    var goal by rememberSaveable { mutableStateOf("") }
    var platform by rememberSaveable { mutableStateOf("YouTube") }
    var brief by rememberSaveable { mutableStateOf("") }
    var error by rememberSaveable { mutableStateOf("") }
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
    ) {
        Text("CREATOR BRIEF", color = DominionGold, fontSize = 13.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 2.sp)
        Spacer(Modifier.height(12.dp))
        Text("Turn the idea into an executable brief.", fontSize = 30.sp, lineHeight = 34.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(10.dp))
        Text(
            "This tool generates a local planning brief on the device. It does not claim to publish, schedule, or contact a remote agent.",
            color = DominionMuted,
            lineHeight = 22.sp,
        )
        Spacer(Modifier.height(22.dp))

        OutlinedTextField(
            value = offer,
            onValueChange = { offer = it.take(240) },
            label = { Text("What are you promoting?") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = false,
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = audience,
            onValueChange = { audience = it.take(240) },
            label = { Text("Who is it for?") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = false,
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = goal,
            onValueChange = { goal = it.take(180) },
            label = { Text("Primary goal") },
            placeholder = { Text("Example: get qualified beta applications") },
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(18.dp))
        Text("Primary platform", fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("YouTube", "TikTok", "Instagram").forEach { option ->
                FilterChip(
                    selected = platform == option,
                    onClick = { platform = option },
                    label = { Text(option) },
                )
            }
        }
        Spacer(Modifier.height(8.dp))
        FilterChip(
            selected = platform == "Facebook",
            onClick = { platform = "Facebook" },
            label = { Text("Facebook") },
        )
        Spacer(Modifier.height(20.dp))
        Button(
            onClick = {
                if (offer.isBlank() || audience.isBlank() || goal.isBlank()) {
                    error = "Complete the offer, audience, and goal before generating the brief."
                    brief = ""
                } else {
                    error = ""
                    brief = buildCreatorBrief(offer.trim(), audience.trim(), goal.trim(), platform)
                }
            },
            colors = ButtonDefaults.buttonColors(containerColor = DominionGold),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Generate brief", fontWeight = FontWeight.Bold)
        }

        if (error.isNotBlank()) {
            Spacer(Modifier.height(12.dp))
            Text(error, color = Color(0xFFFFB4AB), fontSize = 14.sp)
        }

        if (brief.isNotBlank()) {
            Spacer(Modifier.height(24.dp))
            Card(colors = CardDefaults.cardColors(containerColor = DominionPanel)) {
                Column(Modifier.padding(18.dp)) {
                    Text("YOUR BRIEF", color = DominionGold, fontSize = 12.sp, fontWeight = FontWeight.ExtraBold)
                    Spacer(Modifier.height(10.dp))
                    Text(brief, lineHeight = 22.sp)
                }
            }
            Spacer(Modifier.height(12.dp))
            OutlinedButton(
                onClick = {
                    val share = Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(Intent.EXTRA_SUBJECT, "Dominion Creator Brief")
                        putExtra(Intent.EXTRA_TEXT, brief)
                    }
                    context.startActivity(Intent.createChooser(share, "Share creator brief"))
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Share brief")
            }
        }
        Spacer(Modifier.height(32.dp))
    }
}

private fun buildCreatorBrief(offer: String, audience: String, goal: String, platform: String): String {
    return """
        Campaign objective
        $goal

        Offer
        $offer

        Audience
        $audience

        Primary platform
        $platform

        Content angle
        Lead with the audience's immediate problem, show the offer in action, and close with one clear next step tied to the campaign objective.

        Three-post sequence
        1. Problem: name the costly or frustrating problem in plain language.
        2. Proof: demonstrate the workflow, result, or evidence without exaggerated claims.
        3. Action: answer the strongest objection and give one specific call to action.

        Production rule
        Keep each post focused on one promise and one CTA. Measure completed outcomes, not vanity reach alone.
    """.trimIndent()
}

@Composable
private fun AboutScreen() {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
    ) {
        Text("ABOUT", color = DominionGold, fontSize = 13.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 2.sp)
        Spacer(Modifier.height(12.dp))
        Text("Dominion Creator", fontSize = 32.sp, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(14.dp))
        Text(
            "A phone-first creator workflow product built under RADAH MEMSHALAH governance. Consumer functionality stays separate from Dominion's private operator control plane.",
            color = DominionMuted,
            lineHeight = 23.sp,
        )
        Spacer(Modifier.height(24.dp))
        Text("Beta build 0.1.0", fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(
            "No guaranteed growth, revenue, publishing, or automation claim is made by this local beta shell. Remote actions will only be enabled when authenticated public API, authorization, idempotency, and receipt loops are proven.",
            color = DominionMuted,
            lineHeight = 21.sp,
        )
        Spacer(Modifier.height(24.dp))
        Text("Package ID", fontWeight = FontWeight.Bold)
        Text("org.dominionhealing.creator (provisional until Play Console registration)", color = DominionMuted)
        Spacer(Modifier.height(16.dp))
        Text("Target", fontWeight = FontWeight.Bold)
        Text("Android 16 / API 36", color = DominionMuted)
    }
}
