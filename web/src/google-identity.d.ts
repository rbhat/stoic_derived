interface GoogleIdConfiguration {
  client_id: string;
  login_uri: string;
  ux_mode: "redirect";
}

interface GoogleButtonConfiguration {
  type: "standard";
  theme: "outline";
  size: "large";
  text: "sign_in_with";
  shape: "rectangular";
  logo_alignment: "left";
  width: number;
}

interface GoogleAccountsId {
  initialize(config: GoogleIdConfiguration): void;
  renderButton(element: HTMLElement, config: GoogleButtonConfiguration): void;
}

interface Window {
  google?: {
    accounts: {
      id: GoogleAccountsId;
    };
  };
}
