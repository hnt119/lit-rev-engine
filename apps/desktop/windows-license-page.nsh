; Microsoft-component-only agreement for the owner-authorized Windows release.
; This interaction does not relicense the MIT application or establish that the
; owner personally acquired a Visual Studio/SDK license.
!ifndef LITREV_MICROSOFT_TERMS_PAGE
!define LITREV_MICROSOFT_TERMS_PAGE
!include "WinMessages.nsh"
Var LitRevMicrosoftTermsAccepted

!macro LitRevRequireInteractiveMicrosoftTerms
  StrCpy $LitRevMicrosoftTermsAccepted "0"
  ; /S skips page callbacks. Reject it before installer-controlled application/registry/payload writes;
  ; no command-line acceptance token or unattended acceptance route exists.
  IfSilent 0 +3
    SetErrorLevel 2
    Abort
!macroend

!macro LitRevRequireAcceptedMicrosoftTerms
  ; Must be the first instruction in the Application section.
  StrCmp $LitRevMicrosoftTermsAccepted "1" +4
    MessageBox MB_ICONSTOP "Installation requires your explicit agreement to the Microsoft-component terms. Nothing was installed."
    SetErrorLevel 2
    Abort
!macroend

!macro LitRevMicrosoftTermsPage TERMSFILE
  !define MUI_LICENSEPAGE_CHECKBOX
  !define MUI_LICENSEPAGE_CHECKBOX_TEXT "I agree to the displayed terms for the Microsoft components only."
  !define MUI_LICENSEPAGE_TEXT_TOP "Microsoft components only: review the protective terms and complete vendor texts below. Original engine MIT, Python, FFmpeg and other component rights are separate. Cancel if you do not agree."
  !define MUI_PAGE_CUSTOMFUNCTION_SHOW LitRevMicrosoftTermsShow
  !define MUI_PAGE_CUSTOMFUNCTION_LEAVE LitRevMicrosoftTermsLeave
  !insertmacro MUI_PAGE_LICENSE "${TERMSFILE}"

  Function LitRevMicrosoftTermsShow
    StrCpy $LitRevMicrosoftTermsAccepted "0"
    Push $0
    ; NSIS 3.13 Source/exehead/resource.h: IDC_LICENSEAGREE = 1034.
    ; Explicitly reset on every visit; never programmatically preselect Agree.
    GetDlgItem $0 $mui.LicensePage 1034
    SendMessage $0 ${BM_SETCHECK} ${BST_UNCHECKED} 0
    GetDlgItem $0 $HWNDPARENT 1
    EnableWindow $0 0
    Pop $0
  FunctionEnd

  Function LitRevMicrosoftTermsLeave
    Push $0
    Push $1
    GetDlgItem $0 $mui.LicensePage 1034
    StrCmp $0 0 litrev_ms_terms_not_accepted
    SendMessage $0 ${BM_GETCHECK} 0 0 $1
    StrCmp $1 ${BST_CHECKED} litrev_ms_terms_accepted
    litrev_ms_terms_not_accepted:
      StrCpy $LitRevMicrosoftTermsAccepted "0"
      Pop $1
      Pop $0
      MessageBox MB_ICONEXCLAMATION "Select the Microsoft-component agreement checkbox to continue, or Cancel installation."
      Abort
    litrev_ms_terms_accepted:
      StrCpy $LitRevMicrosoftTermsAccepted "1"
      Pop $1
      Pop $0
  FunctionEnd
!macroend
!endif
