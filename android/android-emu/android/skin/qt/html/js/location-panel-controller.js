class LocationPanelController extends GoogleMapPageComponent {
    constructor(expandedCssClassName, collapsedClassName, actionButtonPanelHiddenCssClassName) {
        super();
        this.panelExpandedCssClassName = expandedCssClassName;
        this.panelCollapsedCssClassName = collapsedClassName;
        this.actionButtonPanelHiddenCssClassName = actionButtonPanelHiddenCssClassName;
        this.shouldHideActionButtonPanel = false;
    }

    onMapInitialized(mapManager, eventBus) {
        const self = this;
        $('#floating-action-button').click(() => {
            eventBus.dispatch('floatingActionButtonClicked')
        });
        $('#location-panel-close-button').click(() => {
            self.hide();
        });
    }

    show(address, latLng, elevation, hideActionButtonPanel) {
        console.log('LocationPanelController::show called', address, latLng, elevation, hideActionButtonPanel);
        const latitude = latLng.lat().toFixed(4);
        const longitude = latLng.lng().toFixed(4);
        const subtitle = latitude + ', ' + longitude + (elevation != null ? ', ' + elevation.toFixed(4) : '');
        $('#floating-action-button').show();
        $('#location-panel-close-button').hide();
        $('#location-title').html(address);
        $('#location-subtitle').html(subtitle);
        if (hideActionButtonPanel) {
            $('#location-panel').removeClass().addClass(this.actionButtonPanelHiddenCssClassName);
        }
        else {
            $('#location-panel').removeClass().addClass(this.panelExpandedCssClassName);
        }
        $('#location-action-button-container').css('display', hideActionButtonPanel ? 'none' : 'flex');
    }

    showTitleSubtitle(title, subtitle, hideActionButtonPanel) {
        $('#floating-action-button').hide();
        $('#location-panel-close-button').show();
        $('#location-title').html(title);
        $('#location-subtitle').html(subtitle);
        if (hideActionButtonPanel) {
            $('#location-panel').removeClass().addClass(this.actionButtonPanelHiddenCssClassName);
        }
        else {
            $('#location-panel').removeClass().addClass(this.panelExpandedCssClassName);
        }
        $('#location-action-button-container').css('display', hideActionButtonPanel ? 'none' : 'flex');
    }

    hide() {
        $('#location-panel').removeClass().addClass(this.panelCollapsedCssClassName);
    }
}