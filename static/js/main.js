// Function to handle switching tabs in the Member and Admin dashboards
function showTab(tabId, btnElement) {
    // 1. Hide all panels on the screen
    const panels = document.querySelectorAll('.panel');
    panels.forEach(panel => panel.classList.add('hidden'));
    
    // 2. Remove the 'active' highlight from all buttons
    const buttons = document.querySelectorAll('.nav-tabs button');
    buttons.forEach(btn => btn.classList.remove('active'));
    
    // 3. Show the specific panel requested
    document.getElementById(tabId).classList.remove('hidden');
    
    // 4. Highlight the button that was clicked
    btnElement.classList.add('active');
}